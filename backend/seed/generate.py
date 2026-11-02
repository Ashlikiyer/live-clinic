"""Pure generator for seeded busy appointments. No I/O, so it is fully unit-tested."""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.clinic import OPEN_WEEKDAYS, SLOT_MINUTES, VISIT_MINUTES, VisitType
from app.scheduling.availability import day_blocks

FILL_RATE = 0.5
ANNUAL_CHECKUP_RATE = 0.15


@dataclass(frozen=True)
class GeneratedAppointment:
    doctor_id: str
    patient_index: int
    start: datetime
    end: datetime
    visit_type: VisitType


def generate_appointments(
    *,
    first_day: date,
    days: int,
    doctor_ids: Sequence[str],
    pediatrics_doctor_id: str,
    patient_count: int,
    tz: ZoneInfo,
    rng_seed: int = 42,
) -> list[GeneratedAppointment]:
    """Fill about FILL_RATE of open slots with deterministic fake appointments."""
    rng = random.Random(rng_seed)
    result: list[GeneratedAppointment] = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        if day.weekday() not in OPEN_WEEKDAYS:
            continue
        for doctor_id in doctor_ids:
            for block in day_blocks():
                i = 0
                while i < len(block):
                    if rng.random() >= FILL_RATE:
                        i += 1
                        continue
                    visit_type = _pick_visit_type(
                        rng, doctor_id == pediatrics_doctor_id, can_be_long=i + 1 < len(block)
                    )
                    start = datetime.combine(day, block[i], tzinfo=tz)
                    minutes = VISIT_MINUTES[visit_type]
                    result.append(
                        GeneratedAppointment(
                            doctor_id=doctor_id,
                            patient_index=rng.randrange(patient_count),
                            start=start,
                            end=start + timedelta(minutes=minutes),
                            visit_type=visit_type,
                        )
                    )
                    i += minutes // SLOT_MINUTES
    return result


def _pick_visit_type(rng: random.Random, pediatrics: bool, can_be_long: bool) -> VisitType:
    if pediatrics:
        return VisitType.PEDIATRIC_CONSULT
    if can_be_long and rng.random() < ANNUAL_CHECKUP_RATE:
        return VisitType.ANNUAL_CHECKUP
    return rng.choice([VisitType.GENERAL_CONSULT, VisitType.FOLLOW_UP])
