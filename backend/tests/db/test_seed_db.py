"""Runs the real seed script against Postgres. Skipped when no database is reachable."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClinicInfo, Doctor, SeedAppointment, SeedPatient
from app.db.session import check_database, get_engine, get_sessionmaker
from seed.__main__ import seed


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    if not await check_database():
        pytest.skip("Postgres not reachable at DATABASE_URL")
    async with get_sessionmaker()() as session:
        yield session
    await get_engine().dispose()


async def _count(db: AsyncSession, model: type) -> int:
    return int(await db.scalar(select(func.count()).select_from(model)) or 0)


async def test_seed_is_repeatable(db: AsyncSession) -> None:
    first = await seed(db)
    second = await seed(db)
    assert first == second
    assert await _count(db, Doctor) == 3
    assert await _count(db, ClinicInfo) == first["clinic_info"]
    assert await _count(db, SeedPatient) == 12
    assert await _count(db, SeedAppointment) == first["seed_appointments"] > 0
