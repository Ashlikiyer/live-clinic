"""BookingRepository against real Postgres (skipped when no database is reachable)."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.core.clinic import VisitType
from app.db.models import Doctor, SandboxAppointment, SeedAppointment, SeedPatient
from app.db.session import check_database, get_engine, get_sessionmaker
from app.repositories.booking import Booking, BookingRepository, Moved, patient_ref
from app.repositories.calls import SqlCallStore
from app.scheduling.availability import Interval, free_slots, is_free
from app.scheduling.booking import Rejection
from seed.__main__ import seed

TZ = ZoneInfo("Asia/Manila")


@pytest.fixture
async def repo() -> AsyncIterator[BookingRepository]:
    if not await check_database():
        pytest.skip("Postgres not reachable at DATABASE_URL")
    async with get_sessionmaker()() as db:
        if not await db.scalar(select(func.count()).select_from(Doctor)):
            await seed(db)
    yield BookingRepository(get_sessionmaker(), TZ)
    await get_engine().dispose()


async def new_session() -> uuid.UUID:
    session_id = uuid.uuid4()
    await SqlCallStore(get_sessionmaker()).create_session(
        session_id, f"tok-{session_id.hex}", "ip-test", datetime.now(UTC) + timedelta(hours=24)
    )
    return session_id


def open_day(offset: int) -> date:
    day = datetime.now(TZ).date() + timedelta(days=offset)
    return day + timedelta(days=1) if day.weekday() == 6 else day


async def free_slot(
    repo: BookingRepository, session_id: uuid.UUID, offset: int = 3, skip: int = 0
) -> Interval:
    now = datetime.now(TZ)
    day = open_day(offset)
    busy = await repo.busy(session_id, day, day, now)
    slots = free_slots(
        date_from=day,
        date_to=day,
        now=now,
        tz=TZ,
        doctor_ids=["dr-reyes", "dr-santos"],
        visit_type=VisitType.GENERAL_CONSULT,
        part_of_day="any",
        busy=busy,
    )
    assert len(slots) > skip, "the seeded schedule should leave free slots"
    return slots[skip]


async def hold(repo: BookingRepository, session_id: uuid.UUID, slot: Interval) -> Booking:
    result = await repo.hold(
        session_id,
        doctor_id=slot.doctor_id,
        start=slot.start,
        end=slot.end,
        visit_type=VisitType.GENERAL_CONSULT,
        now=datetime.now(TZ),
    )
    assert not isinstance(result, Rejection), result
    return result[0]


async def test_hold_then_confirm(repo: BookingRepository) -> None:
    session_id = await new_session()
    slot = await free_slot(repo, session_id)
    held = await hold(repo, session_id, slot)
    assert held.status == "holding" and held.hold_expires_at is not None

    ref = patient_ref("Juan Dela Cruz", date(1990, 3, 3))
    booked = await repo.confirm(
        session_id, held.id, patient_name="Juan Dela Cruz", patient_ref=ref, now=datetime.now(TZ)
    )
    assert isinstance(booked, Booking)
    assert booked.status == "confirmed" and booked.patient_name == "Juan Dela Cruz"

    busy = await repo.busy(session_id, slot.start.date(), slot.start.date(), datetime.now(TZ))
    assert not is_free(slot.doctor_id, slot.start, slot.end, busy)
    match = await repo.find_patient(
        session_id, "juan dela cruz", date(1990, 3, 3), datetime.now(TZ)
    )
    assert match is not None and [a.id for a in match.appointments] == [booked.id]


async def test_concurrent_holds_cannot_double_book(repo: BookingRepository) -> None:
    session_id = await new_session()
    slot = await free_slot(repo, session_id)
    now = datetime.now(TZ)

    async def attempt() -> tuple[Booking, list[str]] | Rejection:
        return await repo.hold(
            session_id,
            doctor_id=slot.doctor_id,
            start=slot.start,
            end=slot.end,
            visit_type=VisitType.GENERAL_CONSULT,
            now=now,
        )

    results = await asyncio.gather(*(attempt() for _ in range(4)))
    assert sum(not isinstance(r, Rejection) for r in results) == 1
    async with get_sessionmaker()() as db:
        active = await db.scalar(
            select(func.count())
            .select_from(SandboxAppointment)
            .where(
                SandboxAppointment.session_id == session_id,
                SandboxAppointment.status == "holding",
            )
        )
    assert active == 1


async def test_new_hold_releases_the_previous_one(repo: BookingRepository) -> None:
    session_id = await new_session()
    first = await hold(repo, session_id, await free_slot(repo, session_id, skip=0))
    second = await free_slot(repo, session_id, skip=1)
    result = await repo.hold(
        session_id,
        doctor_id=second.doctor_id,
        start=second.start,
        end=second.end,
        visit_type=VisitType.GENERAL_CONSULT,
        now=datetime.now(TZ),
    )
    assert not isinstance(result, Rejection)
    assert result[1] == [first.id]


async def test_expired_or_foreign_holds_cannot_be_confirmed(repo: BookingRepository) -> None:
    owner, stranger = await new_session(), await new_session()
    held = await hold(repo, owner, await free_slot(repo, owner))
    later = datetime.now(TZ) + timedelta(minutes=6)
    expired = await repo.confirm(owner, held.id, patient_name="A", patient_ref="x", now=later)
    assert isinstance(expired, Rejection) and expired.code == "HOLD_EXPIRED"

    held = await hold(repo, owner, await free_slot(repo, owner, skip=1))
    foreign = await repo.confirm(
        stranger, held.id, patient_name="A", patient_ref="x", now=datetime.now(TZ)
    )
    assert isinstance(foreign, Rejection) and foreign.code == "HOLD_NOT_FOUND"
    assert isinstance(await repo.release(stranger, held.id), Rejection)


async def test_a_seeded_slot_cannot_be_held(repo: BookingRepository) -> None:
    session_id = await new_session()
    taken = await _future_seed(repo)
    result = await repo.hold(
        session_id,
        doctor_id=taken.doctor_id,
        start=taken.start,
        end=taken.end,
        visit_type=VisitType(taken.visit_type)
        if taken.visit_type != "annual_checkup"
        else VisitType.ANNUAL_CHECKUP,
        now=datetime.now(TZ),
    )
    assert isinstance(result, Rejection) and result.code in {"SLOT_TAKEN", "WRONG_DOCTOR"}


async def test_reschedule_own_booking(repo: BookingRepository) -> None:
    session_id = await new_session()
    old_slot = await free_slot(repo, session_id, skip=0)
    held = await hold(repo, session_id, old_slot)
    booked = await repo.confirm(
        session_id,
        held.id,
        patient_name="Ana",
        patient_ref="caller:ana|2000-01-01",
        now=datetime.now(TZ),
    )
    assert isinstance(booked, Booking)
    new_hold = await hold(repo, session_id, await free_slot(repo, session_id, offset=4))

    moved = await repo.reschedule(session_id, booked.id, new_hold.id, datetime.now(TZ))
    assert isinstance(moved, Moved)
    assert moved.appointment.id == booked.id
    assert moved.from_start == old_slot.start
    assert moved.appointment.start == new_hold.start
    assert moved.released_hold_id == new_hold.id
    busy = await repo.busy(
        session_id, old_slot.start.date(), new_hold.start.date(), datetime.now(TZ)
    )
    assert is_free(old_slot.doctor_id, old_slot.start, old_slot.end, busy)
    assert not is_free(new_hold.doctor_id, new_hold.start, new_hold.end, busy)


async def test_seeded_appointment_cancel_and_move_only_affect_this_session(
    repo: BookingRepository,
) -> None:
    mine, other = await new_session(), await new_session()
    appt = await _future_seed(repo)
    public_id = f"seed-{appt.id}"
    now = datetime.now(TZ)
    day = appt.start.astimezone(TZ).date()

    # Move it, then cancel it: it keeps its seed id throughout.
    new_hold = await hold(repo, mine, await free_slot(repo, mine, offset=5))
    moved = await repo.reschedule(mine, public_id, new_hold.id, now)
    assert isinstance(moved, Moved) and moved.appointment.id == public_id
    cancelled = await repo.cancel(mine, public_id, now)
    assert isinstance(cancelled, Booking) and cancelled.id == public_id
    assert cancelled.status == "cancelled"
    again = await repo.cancel(mine, public_id, now)
    assert isinstance(again, Rejection) and again.code == "APPOINTMENT_NOT_FOUND"

    # This session sees the original slot free; another session still sees it taken.
    assert is_free(appt.doctor_id, appt.start, appt.end, await repo.busy(mine, day, day, now))
    assert not is_free(appt.doctor_id, appt.start, appt.end, await repo.busy(other, day, day, now))


async def test_find_seeded_patient_lists_upcoming_visits(repo: BookingRepository) -> None:
    session_id = await new_session()
    appt = await _future_seed(repo)
    async with get_sessionmaker()() as db:
        patient = await db.get(SeedPatient, appt.patient_id)
    assert patient is not None
    match = await repo.find_patient(
        session_id, patient.full_name.upper(), patient.date_of_birth, datetime.now(TZ)
    )
    assert match is not None and match.full_name == patient.full_name
    assert f"seed-{appt.id}" in [a.id for a in match.appointments]
    assert (
        await repo.find_patient(session_id, "Nobody Here", date(1900, 1, 1), datetime.now(TZ))
        is None
    )


async def test_intake_form_marks_corrections(repo: BookingRepository) -> None:
    session_id = await new_session()
    store = SqlCallStore(get_sessionmaker())
    call_id = uuid.uuid4()
    await store.create_call(call_id, session_id, "kokoro")

    first = await repo.update_form(call_id, {"full_name": "Juan", "date_of_birth": "May 3, 1990"})
    assert first == [("full_name", "Juan", False), ("date_of_birth", "May 3, 1990", False)]
    second = await repo.update_form(
        call_id, {"date_of_birth": "March 3, 1990", "full_name": "Juan"}
    )
    assert second == [("date_of_birth", "March 3, 1990", True)]
    form = await repo.form(call_id)
    assert form["date_of_birth"] == {"value": "March 3, 1990", "corrected": True}
    assert form["full_name"] == {"value": "Juan", "corrected": False}


async def _future_seed(repo: BookingRepository) -> SeedAppointment:
    """An adult seeded appointment a few days out."""
    start = datetime.now(TZ) + timedelta(days=2)
    async with get_sessionmaker()() as db:
        row = await db.scalar(
            select(SeedAppointment)
            .where(
                SeedAppointment.start > start,
                SeedAppointment.doctor_id != "dr-cruz",
                SeedAppointment.visit_type == "general_consult",
            )
            .order_by(SeedAppointment.start)
        )
    assert row is not None
    return row
