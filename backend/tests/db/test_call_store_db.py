"""SqlCallStore against real Postgres. Skipped when no database is reachable."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from app.db.session import check_database, get_engine, get_sessionmaker
from app.repositories.calls import SqlCallStore


@pytest.fixture
async def store() -> AsyncIterator[SqlCallStore]:
    if not await check_database():
        pytest.skip("Postgres not reachable at DATABASE_URL")
    yield SqlCallStore(get_sessionmaker())
    await get_engine().dispose()


async def test_call_lifecycle_round_trip(store: SqlCallStore) -> None:
    session_a, session_b = uuid.uuid4(), uuid.uuid4()
    ip_hash = f"test-{uuid.uuid4().hex}"
    expires = datetime.now(UTC) + timedelta(hours=24)
    await store.create_session(session_a, f"tok-{session_a.hex}", ip_hash, expires)
    await store.create_session(session_b, f"tok-{session_b.hex}", "other-ip", expires)

    found = await store.find_session(f"tok-{session_a.hex}")
    assert found is not None and found.id == session_a
    since = datetime.now(UTC) - timedelta(days=1)
    assert await store.count_sessions_since(ip_hash, since) == 1

    call_id = uuid.uuid4()
    await store.create_call(call_id, session_a, "kokoro")
    assert await store.count_calls_since(ip_hash, since) == 1
    assert await store.open_call_for_session(call_id, session_a)
    # Another session can never reach this call.
    assert not await store.open_call_for_session(call_id, session_b)

    user_turn, reply_turn = uuid.uuid4(), uuid.uuid4()
    await store.add_turn(user_turn, call_id, 0, "user", "Hello")
    await store.add_turn(reply_turn, call_id, 1, "assistant", "Hi there, how can I help?")
    await store.update_turn(reply_turn, "Hi there", interrupted=True)
    stages: dict[str, int | None] = {
        "vad_wait_ms": 600,
        "upload_ms": 80,
        "stt_ms": 300,
        "llm_ttft_ms": 250,
        "first_sentence_ms": 120,
        "tts_ms": None,
    }
    await store.save_metrics(reply_turn, stages, 1500)

    turns = await store.list_turns(call_id)
    assert [(t.role, t.text, t.interrupted) for t in turns] == [
        ("user", "Hello", False),
        ("assistant", "Hi there", True),
    ]

    await store.end_call(call_id, "info_only", "Asked a question.", 1)
    assert not await store.open_call_for_session(call_id, session_a)
