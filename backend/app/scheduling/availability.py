"""Free-slot rules. Pure functions, no I/O: everything they need is passed in.

A slot is free for a session if it is inside clinic hours and the booking window, not at lunch,
not taken in the seeded schedule (unless this session cancelled or moved that appointment), and
not held or confirmed in the session's own sandbox.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from app.core.clinic import (
    BOOKING_WINDOW_DAYS,
    CLOSE_TIME,
    LUNCH_END,
    LUNCH_START,
    MIN_LEAD_MINUTES,
    OPEN_TIME,
    OPEN_WEEKDAYS,
    PEDIATRICS_DOCTOR_ID,
    SLOT_MINUTES,
    VISIT_MINUTES,
    AppointmentStatus,
    VisitType,
)

PartOfDay = Literal["morning", "afternoon", "any"]
DEFAULT_SLOT_LIMIT = 6


@dataclass(frozen=True)
class Interval:
    doctor_id: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class SeedBooking:
    id: int
    doctor_id: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class SandboxBooking:
    id: str
    doctor_id: str
    start: datetime
    end: datetime
    status: str
    hold_expires_at: datetime | None = None
    replaces_seed_id: int | None = None

    def is_active_hold(self, now: datetime) -> bool:
        return (
            self.status == AppointmentStatus.HOLDING
            and self.hold_expires_at is not None
            and self.hold_expires_at > now
        )

    def blocks_slot(self, now: datetime) -> bool:
        return self.status == AppointmentStatus.CONFIRMED or self.is_active_hold(now)


# ---------- clinic calendar ----------


def _block_starts(block_start: time, block_end: time) -> list[time]:
    starts: list[time] = []
    cursor = datetime.combine(date.min, block_start)
    end = datetime.combine(date.min, block_end)
    while cursor + timedelta(minutes=SLOT_MINUTES) <= end:
        starts.append(cursor.time())
        cursor += timedelta(minutes=SLOT_MINUTES)
    return starts


def day_blocks() -> list[list[time]]:
    """Slot start times for one clinic day, split into the morning and afternoon blocks."""
    return [_block_starts(OPEN_TIME, LUNCH_START), _block_starts(LUNCH_END, CLOSE_TIME)]


def visit_minutes(visit_type: VisitType) -> int:
    return VISIT_MINUTES[visit_type]


def fits_clinic_hours(start: datetime, minutes: int, tz: ZoneInfo) -> bool:
    """Open day, on a slot boundary, and the whole visit inside one block (no lunch, no close)."""
    local = start.astimezone(tz)
    if local.weekday() not in OPEN_WEEKDAYS or local.second or local.microsecond:
        return False
    end = (local + timedelta(minutes=minutes)).time()
    for block_start, block_end in ((OPEN_TIME, LUNCH_START), (LUNCH_END, CLOSE_TIME)):
        on_grid = local.time() in _block_starts(block_start, block_end)
        if on_grid and end <= block_end and local.time() >= block_start:
            return True
    return False


def in_booking_window(start: datetime, now: datetime, tz: ZoneInfo) -> bool:
    """At least an hour from now, and no later than today + 14 days (clinic time)."""
    last_day = now.astimezone(tz).date() + timedelta(days=BOOKING_WINDOW_DAYS)
    return (
        start >= now + timedelta(minutes=MIN_LEAD_MINUTES)
        and start.astimezone(tz).date() <= last_day
    )


def doctor_allowed(doctor_id: str, visit_type: VisitType) -> bool:
    """Children see the pediatrician; the pediatrician sees only children."""
    return (doctor_id == PEDIATRICS_DOCTOR_ID) == (visit_type == VisitType.PEDIATRIC_CONSULT)


def matches_part_of_day(start: datetime, part_of_day: PartOfDay, tz: ZoneInfo) -> bool:
    t = start.astimezone(tz).time()
    if part_of_day == "morning":
        return t < LUNCH_START
    if part_of_day == "afternoon":
        return t >= LUNCH_END
    return True


# ---------- conflicts ----------


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def effective_busy(
    seed: Iterable[SeedBooking], sandbox: Iterable[SandboxBooking], now: datetime
) -> list[Interval]:
    """Taken intervals as this session sees them: seeded ones it hasn't freed, plus its own."""
    sandbox = list(sandbox)
    freed = {s.replaces_seed_id for s in sandbox if s.replaces_seed_id is not None}
    busy = [Interval(s.doctor_id, s.start, s.end) for s in seed if s.id not in freed]
    busy += [Interval(s.doctor_id, s.start, s.end) for s in sandbox if s.blocks_slot(now)]
    return busy


def is_free(doctor_id: str, start: datetime, end: datetime, busy: Iterable[Interval]) -> bool:
    return not any(b.doctor_id == doctor_id and overlaps(start, end, b.start, b.end) for b in busy)


def free_slots(
    *,
    date_from: date,
    date_to: date,
    now: datetime,
    tz: ZoneInfo,
    doctor_ids: Sequence[str],
    visit_type: VisitType,
    part_of_day: PartOfDay,
    busy: Sequence[Interval],
    limit: int = DEFAULT_SLOT_LIMIT,
) -> list[Interval]:
    """The earliest free slots (up to `limit`) matching the request, in time order."""
    minutes = visit_minutes(visit_type)
    doctors = [d for d in doctor_ids if doctor_allowed(d, visit_type)]
    last_allowed = now.astimezone(tz).date() + timedelta(days=BOOKING_WINDOW_DAYS)
    day = max(date_from, now.astimezone(tz).date())
    found: list[Interval] = []
    while day <= min(date_to, last_allowed) and len(found) < limit:
        for block in day_blocks():
            for slot_time in block:
                start = datetime.combine(day, slot_time, tzinfo=tz)
                end = start + timedelta(minutes=minutes)
                if not (
                    fits_clinic_hours(start, minutes, tz)
                    and in_booking_window(start, now, tz)
                    and matches_part_of_day(start, part_of_day, tz)
                ):
                    continue
                for doctor_id in doctors:
                    if is_free(doctor_id, start, end, busy):
                        found.append(Interval(doctor_id, start, end))
        day += timedelta(days=1)
    return found[:limit]
