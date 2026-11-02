"""Seed the shared clinic data: `uv run python -m seed`.

Re-running replaces all seed rows. Seeded appointments cover the past week and the next
three weeks from today, so re-run it to keep the calendar looking busy.
"""

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import ClinicInfo, Doctor, SeedAppointment, SeedPatient
from app.db.session import get_engine, get_sessionmaker
from seed.data import CLINIC_INFO, DOCTORS, PEDIATRICS_DOCTOR_ID, SEED_PATIENTS
from seed.generate import generate_appointments

DAYS_BEFORE_TODAY = 7
DAYS_AFTER_TODAY = 21


async def seed(db: AsyncSession) -> dict[str, int]:
    tz = ZoneInfo(get_settings().clinic_timezone)
    today = datetime.now(tz).date()

    # Children first so foreign keys never point at deleted rows.
    for model in (SeedAppointment, SeedPatient, ClinicInfo):
        await db.execute(delete(model))
    for doctor in DOCTORS:
        await db.merge(Doctor(**doctor, active=True))

    await db.execute(insert(ClinicInfo), list(CLINIC_INFO))
    patient_ids = list(
        (await db.scalars(insert(SeedPatient).returning(SeedPatient.id), list(SEED_PATIENTS))).all()
    )

    generated = generate_appointments(
        first_day=today - timedelta(days=DAYS_BEFORE_TODAY),
        days=DAYS_BEFORE_TODAY + DAYS_AFTER_TODAY + 1,
        doctor_ids=[d["id"] for d in DOCTORS],
        pediatrics_doctor_id=PEDIATRICS_DOCTOR_ID,
        patient_count=len(patient_ids),
        tz=tz,
    )
    await db.execute(
        insert(SeedAppointment),
        [
            {
                "doctor_id": a.doctor_id,
                "patient_id": patient_ids[a.patient_index],
                "start": a.start,
                "end": a.end,
                "visit_type": a.visit_type.value,
            }
            for a in generated
        ],
    )
    await db.commit()

    doctor_count = len((await db.scalars(select(Doctor.id))).all())
    return {
        "doctors": doctor_count,
        "clinic_info": len(CLINIC_INFO),
        "seed_patients": len(patient_ids),
        "seed_appointments": len(generated),
    }


async def main() -> None:
    async with get_sessionmaker()() as db:
        counts = await seed(db)
    await get_engine().dispose()
    print("Seeded:", ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    asyncio.run(main())
