from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.clinic import VisitType
from app.scheduling.availability import (
    Interval,
    SandboxBooking,
    SeedBooking,
    doctor_allowed,
    effective_busy,
    fits_clinic_hours,
    free_slots,
    in_booking_window,
    is_free,
)

TZ = ZoneInfo("Asia/Manila")
DOCTORS = ["dr-reyes", "dr-cruz", "dr-santos"]
# Monday 2026-11-02, 08:00 clinic time.
NOW = datetime(2026, 11, 2, 8, 0, tzinfo=TZ)
TUE = date(2026, 11, 3)


def at(day: date, hh: int, mm: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=TZ)


def slots(**overrides: object) -> list[Interval]:
    params: dict[str, object] = {
        "date_from": TUE,
        "date_to": TUE,
        "now": NOW,
        "tz": TZ,
        "doctor_ids": DOCTORS,
        "visit_type": VisitType.GENERAL_CONSULT,
        "part_of_day": "any",
        "busy": [],
        "limit": 100,
    }
    params.update(overrides)
    return free_slots(**params)  # type: ignore[arg-type]


# ---------- clinic hours ----------


@pytest.mark.parametrize(
    ("start", "minutes", "ok"),
    [
        (at(TUE, 9), 30, True),
        (at(TUE, 16, 30), 30, True),
        (at(TUE, 8, 30), 30, False),  # before opening
        (at(TUE, 17), 30, False),  # closing time
        (at(TUE, 12), 30, False),  # lunch
        (at(TUE, 12, 30), 30, False),  # lunch
        (at(TUE, 9, 15), 30, False),  # off the 30-minute grid
        (at(TUE, 11, 30), 60, False),  # 60 minutes would run into lunch
        (at(TUE, 16, 30), 60, False),  # 60 minutes would run past closing
        (at(TUE, 11), 60, True),
        (at(date(2026, 11, 8), 10), 30, False),  # Sunday
        (at(date(2026, 11, 7), 10), 30, True),  # Saturday
    ],
)
def test_fits_clinic_hours(start: datetime, minutes: int, ok: bool) -> None:
    assert fits_clinic_hours(start, minutes, TZ) is ok


def test_fits_clinic_hours_accepts_other_timezones() -> None:
    utc = at(TUE, 9).astimezone(ZoneInfo("UTC"))
    assert fits_clinic_hours(utc, 30, TZ)


# ---------- booking window ----------


def test_booking_window_needs_an_hour_of_lead_time() -> None:
    now = at(TUE, 9, 10)
    assert not in_booking_window(at(TUE, 10), now, TZ)
    assert in_booking_window(at(TUE, 10, 30), now, TZ)


def test_booking_window_ends_14_days_out() -> None:
    assert in_booking_window(at(date(2026, 11, 16), 16, 30), NOW, TZ)
    assert not in_booking_window(at(date(2026, 11, 17), 9), NOW, TZ)


# ---------- doctors ----------


def test_children_see_only_the_pediatrician() -> None:
    assert doctor_allowed("dr-cruz", VisitType.PEDIATRIC_CONSULT)
    assert not doctor_allowed("dr-reyes", VisitType.PEDIATRIC_CONSULT)
    assert not doctor_allowed("dr-cruz", VisitType.GENERAL_CONSULT)
    assert doctor_allowed("dr-santos", VisitType.ANNUAL_CHECKUP)


# ---------- conflicts ----------


def test_seeded_and_sandbox_bookings_block_slots() -> None:
    seed = [SeedBooking(1, "dr-reyes", at(TUE, 9), at(TUE, 9, 30))]
    sandbox = [
        SandboxBooking(
            "h1", "dr-reyes", at(TUE, 10), at(TUE, 10, 30), "holding", NOW + timedelta(minutes=5)
        ),
        SandboxBooking("a1", "dr-reyes", at(TUE, 11), at(TUE, 11, 30), "confirmed"),
    ]
    busy = effective_busy(seed, sandbox, NOW)
    for hh in (9, 10, 11):
        assert not is_free("dr-reyes", at(TUE, hh), at(TUE, hh, 30), busy)
    assert is_free("dr-santos", at(TUE, 9), at(TUE, 9, 30), busy)


def test_expired_holds_released_and_cancelled_rows_do_not_block() -> None:
    sandbox = [
        SandboxBooking(
            "h1", "dr-reyes", at(TUE, 9), at(TUE, 9, 30), "holding", NOW - timedelta(seconds=1)
        ),
        SandboxBooking("h2", "dr-reyes", at(TUE, 10), at(TUE, 10, 30), "released"),
        SandboxBooking("c1", "dr-reyes", at(TUE, 11), at(TUE, 11, 30), "cancelled"),
    ]
    assert effective_busy([], sandbox, NOW) == []


def test_cancelled_or_moved_seed_slot_becomes_free_for_this_session() -> None:
    seed = [
        SeedBooking(7, "dr-reyes", at(TUE, 9), at(TUE, 9, 30)),
        SeedBooking(8, "dr-reyes", at(TUE, 10), at(TUE, 10, 30)),
    ]
    sandbox = [
        # Seed 7 cancelled by this session.
        SandboxBooking(
            "c7", "dr-reyes", at(TUE, 9), at(TUE, 9, 30), "cancelled", replaces_seed_id=7
        ),
        # Seed 8 moved to 14:00.
        SandboxBooking(
            "m8", "dr-reyes", at(TUE, 14), at(TUE, 14, 30), "confirmed", replaces_seed_id=8
        ),
    ]
    busy = effective_busy(seed, sandbox, NOW)
    assert is_free("dr-reyes", at(TUE, 9), at(TUE, 9, 30), busy)
    assert is_free("dr-reyes", at(TUE, 10), at(TUE, 10, 30), busy)
    assert not is_free("dr-reyes", at(TUE, 14), at(TUE, 14, 30), busy)


def test_back_to_back_appointments_do_not_overlap() -> None:
    busy = [Interval("dr-reyes", at(TUE, 9), at(TUE, 9, 30))]
    assert is_free("dr-reyes", at(TUE, 9, 30), at(TUE, 10), busy)


# ---------- free_slots ----------


def test_a_free_day_has_14_slots_per_adult_doctor() -> None:
    result = slots()
    assert len(result) == 14 * 2
    assert {s.doctor_id for s in result} == {"dr-reyes", "dr-santos"}
    assert all(not (12 <= s.start.hour < 13) for s in result)
    assert result == sorted(result, key=lambda s: s.start)


def test_pediatric_visits_only_offer_the_pediatrician() -> None:
    assert {s.doctor_id for s in slots(visit_type=VisitType.PEDIATRIC_CONSULT)} == {"dr-cruz"}


def test_part_of_day_filter() -> None:
    assert all(s.start.hour < 12 for s in slots(part_of_day="morning"))
    assert all(s.start.hour >= 13 for s in slots(part_of_day="afternoon"))


def test_sixty_minute_visit_needs_two_consecutive_free_slots() -> None:
    busy = [Interval("dr-reyes", at(TUE, 9, 30), at(TUE, 10))]
    starts = {
        s.start.time()
        for s in slots(visit_type=VisitType.ANNUAL_CHECKUP, doctor_ids=["dr-reyes"], busy=busy)
    }
    assert at(TUE, 9).time() not in starts  # 9:00-10:00 overlaps the 9:30 booking
    assert at(TUE, 9, 30).time() not in starts
    assert at(TUE, 10).time() in starts
    assert at(TUE, 11, 30).time() not in starts  # would run into lunch
    assert at(TUE, 16, 30).time() not in starts  # would run past closing
    for s in slots(visit_type=VisitType.ANNUAL_CHECKUP):
        assert s.end - s.start == timedelta(minutes=60)


def test_same_day_slots_respect_the_one_hour_lead() -> None:
    now = at(TUE, 13, 45)
    result = slots(now=now)
    assert min(s.start for s in result) == at(TUE, 15)


def test_never_offers_past_the_booking_window_or_sundays() -> None:
    result = slots(date_from=date(2026, 11, 8), date_to=date(2026, 11, 30))
    days = {s.start.date() for s in result}
    assert date(2026, 11, 8) not in days  # Sunday
    assert max(days) <= date(2026, 11, 16)


def test_limit_returns_the_earliest_slots() -> None:
    result = slots(limit=6)
    assert len(result) == 6
    assert result[0].start == at(TUE, 9)


def test_fully_booked_day_returns_nothing() -> None:
    busy = [Interval(d, at(TUE, 9), at(TUE, 17)) for d in DOCTORS]
    assert slots(busy=busy) == []
