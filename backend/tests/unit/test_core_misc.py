from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.agent.prompt import build_system_prompt
from app.call.metrics import TurnTiming, call_stats
from app.providers.fake import FakeLLM, FakeSTT, fake_wav
from app.providers.groq_llm import parse_sse_delta
from app.schemas.events import (
    MAX_UTTERANCE_BYTES,
    AudioFrameError,
    CallStart,
    TextMessage,
    build_audio_frame,
    parse_audio_frame,
    parse_client_event,
)

# ---------- prompt ----------


def test_prompt_states_date_and_preview_limits() -> None:
    now = datetime(2026, 11, 3, 14, 5, tzinfo=ZoneInfo("Asia/Manila"))
    prompt = build_system_prompt(now)
    assert "Today is Tuesday, November 3, 2026, 2:05 PM" in prompt
    assert "not connected yet" in prompt
    with_tools = build_system_prompt(now, tools_enabled=True)
    assert "not connected yet" not in with_tools
    # The model gets real dates instead of doing date arithmetic itself.
    assert "Tue 2026-11-03 (today), Wed 2026-11-04" in with_tools
    assert "Tue 2026-11-17" in with_tools


def test_prompt_asks_mia_to_reply_in_the_callers_language() -> None:
    prompt = build_system_prompt(datetime(2026, 11, 3, 14, 5, tzinfo=ZoneInfo("Asia/Manila")))
    assert "reply in the language the caller uses" in prompt
    assert "Taglish" in prompt and '"po"' in prompt


# ---------- metrics ----------


def test_turn_timing_stages_and_total() -> None:
    t = TurnTiming(
        turn_id=3,
        client_start_ts=10_000,
        vad_wait_ms=600,
        received_at=50_700,
        clock_offset_ms=40_000,
        stt_ms=300,
        llm_started_at=51_000,
        first_token_at=51_250,
        first_sentence_at=51_400,
        tts_ms=220,
        first_audio_client_ts=11_700,
    )
    assert t.stages() == {
        "vad_wait_ms": 600,
        "upload_ms": 100,
        "stt_ms": 300,
        "llm_ttft_ms": 250,
        "first_sentence_ms": 150,
        "tts_ms": 220,
    }
    assert t.event_payload()["total_ms"] == 1700


def test_turn_timing_without_audio_falls_back_to_stage_sum() -> None:
    t = TurnTiming(turn_id=1, stt_ms=200, llm_started_at=0, first_token_at=300)
    payload = t.event_payload()
    assert payload["total_ms"] == 500
    assert payload["stages"]["upload_ms"] is None


def test_call_stats() -> None:
    assert call_stats([1200, 1800, 1500], 61.6) == {
        "duration_s": 62,
        "turn_count": 3,
        "median_reply_ms": 1500,
        "slowest_reply_ms": 1800,
    }
    assert call_stats([], 3)["median_reply_ms"] is None


# ---------- events ----------


def test_client_events_are_validated() -> None:
    assert isinstance(parse_client_event('{"type": "call.start", "voice": "lite"}'), CallStart)
    assert isinstance(parse_client_event('{"type": "text.message", "text": "hi"}'), TextMessage)
    assert parse_client_event('{"type": "text.message", "text": "' + "x" * 301 + '"}') is None
    assert parse_client_event('{"type": "nope"}') is None
    assert parse_client_event("not json") is None


def test_audio_frame_round_trip() -> None:
    header = {"type": "audio.utterance", "turn_id": 2, "speech_end_ts": 123, "vad_wait_ms": 600}
    parsed, wav = parse_audio_frame(build_audio_frame(header, b"RIFFdata"))
    assert parsed.turn_id == 2 and parsed.vad_wait_ms == 600
    assert wav == b"RIFFdata"


@pytest.mark.parametrize(
    "frame",
    [
        b"\x00\x00",
        b"\x00\x00\x10\x00{}",
        build_audio_frame({"type": "audio.utterance", "turn_id": 1, "speech_end_ts": 1}, b""),
        build_audio_frame({"type": "wrong", "turn_id": 1, "speech_end_ts": 1}, b"x"),
        build_audio_frame(
            {"type": "audio.utterance", "turn_id": 1, "speech_end_ts": 1},
            b"x" * (MAX_UTTERANCE_BYTES + 1),
        ),
    ],
)
def test_bad_audio_frames_are_rejected(frame: bytes) -> None:
    with pytest.raises(AudioFrameError):
        parse_audio_frame(frame)


# ---------- providers ----------


def test_parse_sse_delta() -> None:
    assert parse_sse_delta('data: {"choices":[{"delta":{"content":"Hi"}}]}') == "Hi"
    assert parse_sse_delta('data: {"choices":[{"delta":{"role":"assistant"}}]}') is None
    assert parse_sse_delta("data: [DONE]") is None
    assert parse_sse_delta(": keep-alive") is None
    assert parse_sse_delta("data: {broken") is None


async def test_fake_providers() -> None:
    assert await FakeSTT().transcribe(fake_wav("book me in")) == "book me in"
    llm = FakeLLM(replies=["Sure thing. Which day?"])
    chunks = [c async for c in llm.stream([]) if isinstance(c, str)]
    assert "".join(chunks) == "Sure thing. Which day?"


def test_database_urls_from_hosts_use_asyncpg() -> None:
    from app.core.config import asyncpg_url

    supabase = "postgresql://postgres.abc:pw@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
    assert asyncpg_url(supabase) == supabase.replace("postgresql://", "postgresql+asyncpg://")
    assert (
        asyncpg_url("postgres://u:p@h/db?sslmode=require")
        == "postgresql+asyncpg://u:p@h/db?ssl=require"
    )
    ready = "postgresql+asyncpg://u:p@h/db?ssl=require"
    assert asyncpg_url(ready) == ready
