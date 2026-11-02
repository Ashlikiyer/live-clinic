"""Booking queries for one session's sandbox, on top of the shared seeded schedule.

Every change runs in one transaction that first locks the session row (SELECT ... FOR UPDATE),
so two fast tool calls in the same session are applied one after the other and can't
double-book. The rules themselves live in app/scheduling (pure); this module only applies them.

Public appointment ids: a session's own booking is its UUID. A seeded appointment is
"seed-<id>", and keeps that id after this session moves it (the sandbox row that replaces it
has `replaces_seed_id`), so the calendar can follow it.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clinic import AppointmentStatus, VisitType
from app.db.models import (
    Doctor,
    IntakeForm,
    SandboxAppointment,
    SandboxSession,
    SeedAppointment,
    SeedPatient,
    ToolCall,
)
from app.scheduling.availability import (
    Interval,
    SandboxBooking,
    SeedBooking,
    effective_busy,
)
from app.scheduling.booking import Rejection, check_hold_usable, check_new_slot, hold_expiry

SEED_PREFIX = "seed-"


@dataclass(frozen=True)
class DoctorInfo:
    id: str
    name: str
    specialty: str
    color: str


@dataclass(frozen=True)
class Booking:
    """A held or booked appointment, as tools and events see it."""

    id: str
    doctor_id: str
    start: datetime
    end: datetime
    visit_type: str
    status: str
    patient_name: str | None = None
    hold_expires_at: datetime | None = None


@dataclass(frozen=True)
class Moved:
    appointment: Booking
    from_start: datetime
    released_hold_id: str


@dataclass(frozen=True)
class PatientMatch:
    full_name: str
    date_of_birth: date
    appointments: list[Booking]


def normalize_name(name: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", name.lower()).split())


def patient_ref(full_name: str, date_of_birth: date) -> str:
    """How a caller-provided patient is stored on sandbox bookings, so find_patient can match."""
    return f"caller:{normalize_name(full_name)}|{date_of_birth.isoformat()}"


def _seed_public_id(seed_id: int) -> str:
    return f"{SEED_PREFIX}{seed_id}"


def _parse_seed_id(public_id: str) -> int | None:
    if public_id.startswith(SEED_PREFIX) and public_id[len(SEED_PREFIX) :].isdigit():
        return int(public_id[len(SEED_PREFIX) :])
    return None


def _parse_uuid(public_id: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(public_id)
    except ValueError:
        return None


def _public_id(row: SandboxAppointment) -> str:
    # A moved seeded appointment keeps its seed id; a cancelled seed row is a tombstone.
    if row.replaces_seed_id is not None and row.status == AppointmentStatus.CONFIRMED:
        return _seed_public_id(row.replaces_seed_id)
    return str(row.id)


def _to_booking(row: SandboxAppointment) -> Booking:
    return Booking(
        id=_public_id(row),
        doctor_id=row.doctor_id,
        start=row.start,
        end=row.end,
        visit_type=row.visit_type,
        status=row.status,
        patient_name=row.patient_name,
        hold_expires_at=row.hold_expires_at,
    )


def _to_sandbox(row: SandboxAppointment) -> SandboxBooking:
    return SandboxBooking(
        id=str(row.id),
        doctor_id=row.doctor_id,
        start=row.start,
        end=row.end,
        status=row.status,
        hold_expires_at=row.hold_expires_at,
        replaces_seed_id=row.replaces_seed_id,
    )


class BookingRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], tz: ZoneInfo) -> None:
        self._sessionmaker = sessionmaker
        self._tz = tz
        self._doctors: list[DoctorInfo] | None = None

    # ---------- reads ----------

    async def doctors(self) -> list[DoctorInfo]:
        if self._doctors is None:
            async with self._sessionmaker() as db:
                rows = await db.scalars(select(Doctor).where(Doctor.active).order_by(Doctor.name))
                self._doctors = [DoctorInfo(d.id, d.name, d.specialty, d.color) for d in rows]
        return self._doctors

    async def busy(
        self, session_id: uuid.UUID, date_from: date, date_to: date, now: datetime
    ) -> list[Interval]:
        async with self._sessionmaker() as db:
            return await self._busy(db, session_id, date_from, date_to, now)

    async def calendar_day(
        self, session_id: uuid.UUID, day: date, now: datetime
    ) -> tuple[list[tuple[str, SeedAppointment]], list[Booking]]:
        """Seeded busy slots this session hasn't freed, plus its own bookings, for one day."""
        async with self._sessionmaker() as db:
            seed = await self._seed_rows(db, day, day)
            rows = await self._sandbox_rows(db, session_id)
        freed = {r.replaces_seed_id for r in rows if r.replaces_seed_id is not None}
        busy_seed = [(_seed_public_id(s.id), s) for s in seed if s.id not in freed]
        own = [
            _to_booking(r)
            for r in rows
            if r.start.astimezone(self._tz).date() == day
            and (_to_sandbox(r).blocks_slot(now) or r.status == AppointmentStatus.CANCELLED)
        ]
        return busy_seed, own

    async def find_patient(
        self, session_id: uuid.UUID, full_name: str, date_of_birth: date, now: datetime
    ) -> PatientMatch | None:
        """A seeded patient or someone booked in this sandbox, with their upcoming visits."""
        name = normalize_name(full_name)
        async with self._sessionmaker() as db:
            rows = await self._sandbox_rows(db, session_id)
            freed = {r.replaces_seed_id for r in rows if r.replaces_seed_id is not None}
            appointments: list[Booking] = []
            patients = await db.scalars(
                select(SeedPatient).where(SeedPatient.date_of_birth == date_of_birth)
            )
            seed_patient = next((p for p in patients if normalize_name(p.full_name) == name), None)
            if seed_patient is not None:
                seed = await db.scalars(
                    select(SeedAppointment)
                    .where(
                        SeedAppointment.patient_id == seed_patient.id, SeedAppointment.start >= now
                    )
                    .order_by(SeedAppointment.start)
                )
                appointments += [
                    Booking(
                        _seed_public_id(s.id),
                        s.doctor_id,
                        s.start,
                        s.end,
                        s.visit_type,
                        AppointmentStatus.CONFIRMED,
                        seed_patient.full_name,
                    )
                    for s in seed
                    if s.id not in freed
                ]
            ref = patient_ref(full_name, date_of_birth)
            seed_refs = {f"seed:{seed_patient.id}"} if seed_patient else set()
            appointments += [
                _to_booking(r)
                for r in rows
                if r.status == AppointmentStatus.CONFIRMED
                and r.start >= now
                and (r.patient_ref == ref or r.patient_ref in seed_refs)
            ]
        if seed_patient is None and not appointments:
            return None
        appointments.sort(key=lambda b: b.start)
        display = seed_patient.full_name if seed_patient else full_name
        return PatientMatch(display, date_of_birth, appointments)

    # ---------- changes ----------

    async def hold(
        self,
        session_id: uuid.UUID,
        *,
        doctor_id: str,
        start: datetime,
        end: datetime,
        visit_type: VisitType,
        now: datetime,
    ) -> tuple[Booking, list[str]] | Rejection:
        """Hold a slot for 5 minutes. Releases the session's other active holds on success."""
        doctor_ids = [d.id for d in await self.doctors()]
        async with self._sessionmaker() as db, db.begin():
            await self._lock(db, session_id)
            day = start.astimezone(self._tz).date()
            rows = await self._sandbox_rows(db, session_id, for_update=True)
            same = next(
                (
                    r
                    for r in rows
                    if r.doctor_id == doctor_id
                    and r.start == start
                    and _to_sandbox(r).is_active_hold(now)
                ),
                None,
            )
            if same is not None:
                return Rejection("ALREADY_HELD", f"That slot is already held as hold_id {same.id}.")
            busy = effective_busy(
                [self._seed_booking(s) for s in await self._seed_rows(db, day, day)],
                [_to_sandbox(r) for r in rows],
                now,
            )
            rejection = check_new_slot(
                doctor_id=doctor_id,
                start=start,
                visit_type=visit_type,
                known_doctors=doctor_ids,
                busy=busy,
                now=now,
                tz=self._tz,
            )
            if rejection:
                return rejection
            released: list[str] = []
            for r in rows:
                if _to_sandbox(r).is_active_hold(now):
                    r.status = AppointmentStatus.RELEASED
                    r.hold_expires_at = None
                    released.append(str(r.id))
            row = SandboxAppointment(
                id=uuid.uuid4(),
                session_id=session_id,
                doctor_id=doctor_id,
                start=start,
                end=end,
                visit_type=visit_type.value,
                status=AppointmentStatus.HOLDING,
                hold_expires_at=hold_expiry(now),
            )
            db.add(row)
        return _to_booking(row), released

    async def confirm(
        self,
        session_id: uuid.UUID,
        hold_id: str,
        *,
        patient_name: str,
        patient_ref: str,
        now: datetime,
    ) -> Booking | Rejection:
        async with self._sessionmaker() as db, db.begin():
            await self._lock(db, session_id)
            row = await self._own_row(db, session_id, hold_id)
            rejection = check_hold_usable(_to_sandbox(row) if row else None, now)
            if rejection or row is None:
                return rejection or Rejection("HOLD_NOT_FOUND", "Hold a slot first.")
            row.status = AppointmentStatus.CONFIRMED
            row.hold_expires_at = None
            row.patient_name = patient_name
            row.patient_ref = patient_ref
        return _to_booking(row)

    async def release(self, session_id: uuid.UUID, hold_id: str) -> Booking | Rejection:
        async with self._sessionmaker() as db, db.begin():
            await self._lock(db, session_id)
            row = await self._own_row(db, session_id, hold_id)
            if row is None or row.status != AppointmentStatus.HOLDING:
                return Rejection("HOLD_NOT_FOUND", "There is no such hold to release.")
            row.status = AppointmentStatus.RELEASED
            row.hold_expires_at = None
        return _to_booking(row)

    async def reschedule(
        self, session_id: uuid.UUID, appointment_id: str, new_hold_id: str, now: datetime
    ) -> Moved | Rejection:
        """Move an appointment into the time held by `new_hold_id`."""
        async with self._sessionmaker() as db, db.begin():
            await self._lock(db, session_id)
            hold = await self._own_row(db, session_id, new_hold_id)
            rejection = check_hold_usable(_to_sandbox(hold) if hold else None, now)
            if rejection or hold is None:
                return rejection or Rejection("HOLD_NOT_FOUND", "Hold the new slot first.")

            target = await self._resolve_appointment(db, session_id, appointment_id, now)
            if isinstance(target, Rejection):
                return target
            hold.status = AppointmentStatus.RELEASED
            hold.hold_expires_at = None
            if isinstance(target, SandboxAppointment):
                from_start = target.start
                target.doctor_id, target.start, target.end = hold.doctor_id, hold.start, hold.end
                target.visit_type = hold.visit_type
                moved = target
            else:
                seed, name = target
                from_start = seed.start
                moved = SandboxAppointment(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    doctor_id=hold.doctor_id,
                    start=hold.start,
                    end=hold.end,
                    visit_type=hold.visit_type,
                    status=AppointmentStatus.CONFIRMED,
                    patient_name=name,
                    patient_ref=f"seed:{seed.patient_id}",
                    replaces_seed_id=seed.id,
                )
                db.add(moved)
        return Moved(_to_booking(moved), from_start, str(hold.id))

    async def cancel(
        self, session_id: uuid.UUID, appointment_id: str, now: datetime
    ) -> Booking | Rejection:
        async with self._sessionmaker() as db, db.begin():
            await self._lock(db, session_id)
            target = await self._resolve_appointment(db, session_id, appointment_id, now)
            if isinstance(target, Rejection):
                return target
            if isinstance(target, SandboxAppointment):
                public_id = _public_id(target)
                target.status = AppointmentStatus.CANCELLED
                return Booking(**{**_to_booking(target).__dict__, "id": public_id})
            seed, name = target
            tombstone = SandboxAppointment(
                id=uuid.uuid4(),
                session_id=session_id,
                doctor_id=seed.doctor_id,
                start=seed.start,
                end=seed.end,
                visit_type=seed.visit_type,
                status=AppointmentStatus.CANCELLED,
                patient_name=name,
                patient_ref=f"seed:{seed.patient_id}",
                replaces_seed_id=seed.id,
            )
            db.add(tombstone)
        return Booking(
            _seed_public_id(seed.id),
            seed.doctor_id,
            seed.start,
            seed.end,
            seed.visit_type,
            AppointmentStatus.CANCELLED,
            name,
        )

    # ---------- intake form and audit ----------

    async def form(self, call_id: uuid.UUID) -> dict[str, dict[str, Any]]:
        async with self._sessionmaker() as db:
            row = await db.scalar(select(IntakeForm).where(IntakeForm.call_id == call_id))
            return dict(row.data) if row else {}

    async def update_form(
        self, call_id: uuid.UUID, values: dict[str, str]
    ) -> list[tuple[str, str, bool]]:
        """Save fields; returns (field, value, corrected) for each field that changed."""
        async with self._sessionmaker() as db, db.begin():
            row = await db.scalar(
                select(IntakeForm).where(IntakeForm.call_id == call_id).with_for_update()
            )
            if row is None:
                row = IntakeForm(id=uuid.uuid4(), call_id=call_id, data={})
                db.add(row)
            data = dict(row.data or {})
            changed: list[tuple[str, str, bool]] = []
            for field, value in values.items():
                old = str(data.get(field, {}).get("value", ""))
                if old == value:
                    continue
                corrected = bool(old) or bool(data.get(field, {}).get("corrected"))
                data[field] = {"value": value, "corrected": corrected}
                changed.append((field, value, corrected))
            row.data = data
        return changed

    async def save_tool_calls(self, turn_id: uuid.UUID, calls: Sequence[dict[str, Any]]) -> None:
        if not calls:
            return
        async with self._sessionmaker() as db, db.begin():
            db.add_all(
                ToolCall(
                    id=uuid.uuid4(),
                    turn_id=turn_id,
                    name=c["name"],
                    args=c["args"],
                    result=c["result"],
                    ok=c["ok"],
                    ms=c["ms"],
                )
                for c in calls
            )

    # ---------- helpers ----------

    async def _lock(self, db: AsyncSession, session_id: uuid.UUID) -> None:
        await db.execute(
            select(SandboxSession.id).where(SandboxSession.id == session_id).with_for_update()
        )

    async def _sandbox_rows(
        self, db: AsyncSession, session_id: uuid.UUID, *, for_update: bool = False
    ) -> list[SandboxAppointment]:
        query = select(SandboxAppointment).where(SandboxAppointment.session_id == session_id)
        if for_update:
            query = query.with_for_update()
        return list(await db.scalars(query))

    async def _seed_rows(self, db: AsyncSession, first: date, last: date) -> list[SeedAppointment]:
        start = datetime.combine(first, datetime.min.time(), tzinfo=self._tz)
        end = datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=self._tz)
        rows = await db.scalars(
            select(SeedAppointment).where(
                SeedAppointment.start >= start, SeedAppointment.start < end
            )
        )
        return list(rows)

    async def _busy(
        self, db: AsyncSession, session_id: uuid.UUID, first: date, last: date, now: datetime
    ) -> list[Interval]:
        seed = await self._seed_rows(db, first, last)
        sandbox = await self._sandbox_rows(db, session_id)
        return effective_busy(
            [self._seed_booking(s) for s in seed], [_to_sandbox(r) for r in sandbox], now
        )

    @staticmethod
    def _seed_booking(row: SeedAppointment) -> SeedBooking:
        return SeedBooking(row.id, row.doctor_id, row.start, row.end)

    async def _own_row(
        self, db: AsyncSession, session_id: uuid.UUID, public_id: str
    ) -> SandboxAppointment | None:
        row_id = _parse_uuid(public_id)
        if row_id is None:
            return None
        return await db.scalar(
            select(SandboxAppointment)
            .where(SandboxAppointment.id == row_id, SandboxAppointment.session_id == session_id)
            .with_for_update()
        )

    async def _resolve_appointment(
        self, db: AsyncSession, session_id: uuid.UUID, public_id: str, now: datetime
    ) -> SandboxAppointment | tuple[SeedAppointment, str] | Rejection:
        """A confirmed upcoming appointment this session may change."""
        not_found = Rejection(
            "APPOINTMENT_NOT_FOUND",
            "No upcoming appointment with that id. Use an appointment_id from find_patient.",
        )
        seed_id = _parse_seed_id(public_id)
        if seed_id is not None:
            moved = await db.scalar(
                select(SandboxAppointment)
                .where(
                    SandboxAppointment.session_id == session_id,
                    SandboxAppointment.replaces_seed_id == seed_id,
                )
                .with_for_update()
            )
            if moved is not None:
                if moved.status != AppointmentStatus.CONFIRMED or moved.start < now:
                    return not_found
                return moved
            seed = await db.get(SeedAppointment, seed_id)
            if seed is None or seed.start < now:
                return not_found
            patient = await db.get(SeedPatient, seed.patient_id)
            return seed, patient.full_name if patient else ""
        row = await self._own_row(db, session_id, public_id)
        if row is None or row.status != AppointmentStatus.CONFIRMED or row.start < now:
            return not_found
        return row
