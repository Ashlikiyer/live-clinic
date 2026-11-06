"""/api/stats and the daily cleanup against real Postgres (skipped when it isn't reachable)."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.models import DailyStats, SandboxSession, SeedAppointment
from app.db.session import check_database, get_engine
from app.main import create_app
from app.providers.base import Providers
from app.providers.fake import FakeLLM, FakeSTT
from app.repositories.calls import SqlCallStore
from app.repositories.stats import StatsRepository

TZ = ZoneInfo("Asia/Manila")
STAGES: dict[str, int | None] = {
    "vad_wait_ms": 600,
    "upload_ms": 20,
    "stt_ms": 640,
    "llm_ttft_ms": 260,
    "first_sentence_ms": 5,
    "tts_ms": 10,
}


def fresh_sessionmaker() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _reachable() -> bool:
    ok = await check_database()
    await get_engine().dispose()
    return ok


@pytest.fixture
def client() -> Iterator[TestClient]:
    if not asyncio.run(_reachable()):
        pytest.skip("Postgres not reachable at DATABASE_URL")
    sessionmaker = fresh_sessionmaker()
    app = create_app(
        store=SqlCallStore(sessionmaker),
        providers=Providers(stt=FakeSTT(), llm=FakeLLM()),
        stats_repo=StatsRepository(sessionmaker, TZ),
    )
    with TestClient(app) as c:
        yield c


async def _expired_call_with_replies(totals: list[int], stop_ms: int | None) -> uuid.UUID:
    """An already-expired session with one finished call and measured replies."""
    store = SqlCallStore(fresh_sessionmaker())
    session_id, call_id = uuid.uuid4(), uuid.uuid4()
    await store.create_session(
        session_id, f"tok-{session_id.hex}", "ip-stats", datetime.now(UTC) - timedelta(minutes=1)
    )
    await store.create_call(call_id, session_id, "kokoro")
    for index, total in enumerate(totals):
        turn_id = uuid.uuid4()
        await store.add_turn(
            turn_id, call_id, index, "assistant", "Hello.", interrupted=bool(stop_ms)
        )
        await store.save_metrics(turn_id, STAGES, total, stop_ms)
    await store.end_call(call_id, "booked", "Booked a visit.", len(totals))
    return session_id


async def _today_rollup() -> tuple[int, int]:
    async with fresh_sessionmaker()() as db:
        row = await db.get(DailyStats, datetime.now(TZ).date())
    return (row.turn_count, row.call_count) if row else (0, 0)


async def _session_exists(session_id: uuid.UUID) -> bool:
    async with fresh_sessionmaker()() as db:
        return (
            await db.scalar(select(SandboxSession.id).where(SandboxSession.id == session_id))
        ) is not None


def test_cleanup_needs_the_cron_secret(client: TestClient) -> None:
    assert client.post("/api/internal/cleanup").status_code == 401
    wrong = client.post("/api/internal/cleanup", headers={"X-Cron-Secret": "nope"})
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "UNAUTHORIZED"


def test_stats_survive_cleanup_through_the_daily_rollup(client: TestClient) -> None:
    secret = {"X-Cron-Secret": get_settings().cron_secret}
    # Start from a cleaned state so the numbers below are only about this test's call.
    client.post("/api/internal/cleanup", headers=secret)
    before: dict[str, Any] = client.get("/api/stats").json()
    turns_before, calls_before = asyncio.run(_today_rollup())

    session_id = asyncio.run(_expired_call_with_replies([1500, 1700, 2600], stop_ms=430))
    live: dict[str, Any] = client.get("/api/stats").json()
    assert live["replies"] == before["replies"] + 3
    assert live["calls"] == before["calls"] + 1
    assert live["interruptions"] == before["interruptions"] + 3
    assert live["daily"][-1]["day"] == datetime.now(TZ).date().isoformat()

    cleaned = client.post("/api/internal/cleanup", headers=secret).json()
    assert cleaned["deleted_sessions"] >= 1
    assert cleaned["rolled_up_turns"] >= 3
    assert not asyncio.run(_session_exists(session_id))
    turns_after, calls_after = asyncio.run(_today_rollup())
    assert (turns_after - turns_before, calls_after - calls_before) == (3, 1)

    # Same numbers, now read from daily_stats instead of the deleted per-turn rows.
    after: dict[str, Any] = client.get("/api/stats").json()
    for key in ("replies", "calls", "interruptions", "median_total_ms", "p95_total_ms"):
        assert after[key] == live[key], key
    assert after["outcomes"] == live["outcomes"]


def test_stats_are_public_and_have_no_transcripts(client: TestClient) -> None:
    body = client.get("/api/stats").json()
    assert body["window_days"] == 7 and len(body["daily"]) == 7
    assert "transcript" not in str(body).lower()
    assert set(body["stage_medians"]) == set(STAGES)


def test_cleanup_tops_up_a_stale_seeded_schedule(client: TestClient) -> None:
    secret = {"X-Cron-Secret": get_settings().cron_secret}
    client.post("/api/internal/cleanup", headers=secret)  # seeds an empty test database
    # A seed that still covers the booking window is left alone.
    assert client.post("/api/internal/cleanup", headers=secret).json()["reseeded"] == 0

    async def age_the_seed() -> None:
        async with fresh_sessionmaker()() as db, db.begin():
            await db.execute(
                delete(SeedAppointment).where(
                    SeedAppointment.start > datetime.now(UTC) + timedelta(days=3)
                )
            )

    asyncio.run(age_the_seed())
    assert client.post("/api/internal/cleanup", headers=secret).json()["reseeded"] == 1

    async def last_seed_start() -> datetime | None:
        async with fresh_sessionmaker()() as db:
            return await db.scalar(select(func.max(SeedAppointment.start)))

    last = asyncio.run(last_seed_start())
    assert last is not None and last > datetime.now(UTC) + timedelta(days=14)
