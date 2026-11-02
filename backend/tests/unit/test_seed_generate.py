import itertools
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.clinic import (
    CLOSE_TIME,
    LUNCH_END,
    LUNCH_START,
    OPEN_TIME,
    VISIT_MINUTES,
    VisitType,
)
from app.scheduling.availability import day_blocks
from seed.generate import GeneratedAppointment, generate_appointments

TZ = ZoneInfo("Asia/Manila")
DOCTORS = ["dr-reyes", "dr-cruz", "dr-santos"]
# 2026-11-02 is a Monday; 28 days covers four Sundays.
FIRST_DAY = date(2026, 11, 2)


def _generate(seed: int = 42) -> list[GeneratedAppointment]:
    return generate_appointments(
        first_day=FIRST_DAY,
        days=28,
        doctor_ids=DOCTORS,
        pediatrics_doctor_id="dr-cruz",
        patient_count=12,
        tz=TZ,
        rng_seed=seed,
    )


def test_day_blocks_skip_lunch() -> None:
    morning, afternoon = day_blocks()
    assert len(morning) == 6 and len(afternoon) == 8
    assert morning[0] == OPEN_TIME and afternoon[0] == LUNCH_END
    assert all(t < LUNCH_START for t in morning)


def test_is_deterministic() -> None:
    assert _generate() == _generate()
    assert _generate(1) != _generate(2)


def test_appointments_stay_inside_clinic_hours_and_outside_lunch() -> None:
    for a in _generate():
        assert a.start.tzinfo == TZ
        assert a.start.weekday() != 6, "closed on Sundays"
        assert a.start.time() >= OPEN_TIME and a.end.time() <= CLOSE_TIME
        overlaps_lunch = a.start.time() < LUNCH_END and a.end.time() > LUNCH_START
        assert not overlaps_lunch
        assert a.end - a.start == timedelta(minutes=VISIT_MINUTES[a.visit_type])


def test_no_double_booking_per_doctor() -> None:
    by_doctor: dict[str, list[GeneratedAppointment]] = defaultdict(list)
    for a in _generate():
        by_doctor[a.doctor_id].append(a)
    for appointments in by_doctor.values():
        appointments.sort(key=lambda a: a.start)
        for prev, nxt in itertools.pairwise(appointments):
            assert prev.end <= nxt.start


def test_roughly_half_of_slots_are_busy() -> None:
    open_days = sum(1 for i in range(28) if (FIRST_DAY + timedelta(days=i)).weekday() != 6)
    total_slots = open_days * len(DOCTORS) * 14
    busy_slots = sum(VISIT_MINUTES[a.visit_type] // 30 for a in _generate())
    assert 0.4 <= busy_slots / total_slots <= 0.65


def test_pediatrician_only_sees_children_visits_and_others_never_do() -> None:
    for a in _generate():
        is_pediatric = a.visit_type is VisitType.PEDIATRIC_CONSULT
        assert is_pediatric == (a.doctor_id == "dr-cruz")


def test_includes_some_hour_long_checkups() -> None:
    assert any(a.visit_type is VisitType.ANNUAL_CHECKUP for a in _generate())


def test_patient_indexes_are_in_range() -> None:
    assert {a.patient_index for a in _generate()} <= set(range(12))
    assert isinstance(_generate()[0].start, datetime)
