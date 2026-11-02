"""Full call turns over the WebSocket with fake providers: frames in, events out."""

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.agent.prompt import GREETING, RECONNECT_LINE, STT_RECOVERY_LINE
from app.core.config import get_settings
from app.providers.fake import FakeLLM, FakeSTT
from app.repositories.calls import MemoryCallStore
from app.routers.call_ws import origin_allowed

from .helpers import (
    new_token,
    receive_until,
    send_utterance,
    start_call,
    text_of,
    wait_for,
)


def test_rejects_missing_or_unknown_token(client: TestClient) -> None:
    for url in ("/ws/call", "/ws/call?token=nope"):
        with client.websocket_connect(url) as ws:
            event = ws.receive_json()
        assert event["type"] == "error"
        assert event["code"] == "SESSION_EXPIRED"
        assert event["retryable"] is False


def test_rejects_foreign_origin(client: TestClient) -> None:
    assert origin_allowed("http://localhost:3000/", "http://localhost:3000")
    assert not origin_allowed("https://evil.example", "http://localhost:3000")


def test_call_start_sends_ready_then_spoken_greeting(client: TestClient) -> None:
    token = new_token(client)
    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        events = start_call(ws)
    assert events[0]["type"] == "call.ready"
    assert events[0]["timezone"] == "Asia/Manila"
    assert text_of(events, 0) == GREETING
    sentences = [e["text"] for e in events if e["type"] == "agent.sentence"]
    assert sentences[0].startswith("Hi, thanks for calling")
    assert " ".join(sentences) == GREETING


def test_audio_turn_flows_through_stt_llm_and_sentences(
    client: TestClient, store: MemoryCallStore, llm: FakeLLM
) -> None:
    llm.replies = ["Sure, I can help. What day works for you?"]
    token = new_token(client)
    speech_end = int(time.time() * 1000)
    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        send_utterance(ws, 1, "I'd like to see a doctor", speech_end)
        events = receive_until(ws, "agent.text.done", turn_id=1)

        types = [e["type"] for e in events]
        assert types[0] == "transcript.user.final"
        assert events[0]["text"] == "I'd like to see a doctor"
        assert types.index("agent.text.delta") < types.index("agent.sentence")
        assert [e["text"] for e in events if e["type"] == "agent.sentence"] == [
            "Sure, I can help.",
            "What day works for you?",
        ]

        ws.send_json(
            {"type": "tts.first_audio", "turn_id": 1, "ts": speech_end + 1400, "tts_ms": 210}
        )
        metrics = receive_until(ws, "metrics.turn")[-1]
        ws.send_json({"type": "call.end", "reason": "user"})
        ended = receive_until(ws, "call.ended")[-1]

    assert metrics["total_ms"] == 1400
    assert metrics["stages"]["vad_wait_ms"] == 600
    assert metrics["stages"]["tts_ms"] == 210
    assert metrics["interrupted"] is False
    assert ended["outcome"] == "info_only"
    assert ended["stats"]["median_reply_ms"] == 1400

    # The LLM saw the system prompt, the greeting and the caller's words.
    roles = [m.role for m in llm.calls[0]]
    assert roles == ["system", "assistant", "user"]

    wait_for(lambda: len(store.metrics) == 1 and any(c["outcome"] for c in store.calls.values()))
    roles_saved = [t["role"] for t in sorted(store.turns.values(), key=lambda t: t["index"])]
    assert roles_saved == ["assistant", "user", "assistant"]


def test_typed_message_uses_the_same_path(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = ["We open at 9 AM."]
    token = new_token(client)
    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        ws.send_json({"type": "text.message", "text": "When do you open?", "ts": 1})
        events = receive_until(ws, "agent.text.done", turn_id=1)
    assert events[0] == {**events[0], "type": "transcript.user.final", "text": "When do you open?"}
    assert text_of(events, 1) == "We open at 9 AM."


def test_emergency_overrides_the_llm_and_ends_the_call(
    client: TestClient, store: MemoryCallStore, llm: FakeLLM
) -> None:
    token = new_token(client)
    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        ws.send_json({"type": "text.message", "text": "I have crushing chest pain", "ts": 1})
        events = receive_until(ws, "call.ended")
    assert "911" in text_of(events, 1)
    assert events[-1]["outcome"] == "emergency_advised"
    assert llm.calls == []
    wait_for(lambda: any(c["outcome"] == "emergency_advised" for c in store.calls.values()))


def test_barge_in_keeps_only_played_text(
    client: TestClient, store: MemoryCallStore, llm: FakeLLM
) -> None:
    long_reply = (
        "I'm holding Wednesday at nine thirty with Dr. Reyes. "
        "That's a general consult, and it lasts thirty minutes. Shall I confirm it for you?"
    )
    llm.replies = [long_reply, "Of course. Which afternoon time suits you?"]
    llm.delay_s = 0.02
    token = new_token(client)
    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        ws.send_json({"type": "text.message", "text": "Wednesday morning please", "ts": 1})
        receive_until(ws, "agent.sentence", turn_id=1)
        ws.send_json(
            {
                "type": "user.interrupt",
                "turn_id": 1,
                "played_text": "I'm holding Wednesday",
                "played_ms": 900,
                "ts": 2,
            }
        )
        metrics = receive_until(ws, "metrics.turn", turn_id=1)[-1]
        ws.send_json({"type": "text.message", "text": "Actually, the afternoon", "ts": 3})
        events = receive_until(ws, "agent.text.done", turn_id=2)

    assert metrics["interrupted"] is True
    # Nothing more was streamed for the interrupted turn after the new turn started.
    assert all(e.get("turn_id") != 1 for e in events if e["type"].startswith("agent."))
    # The next LLM call only "remembers" what the caller actually heard.
    assistant_messages = [m.content for m in llm.calls[1] if m.role == "assistant"]
    assert assistant_messages[-1] == "I'm holding Wednesday [interrupted by caller]"
    wait_for(
        lambda: any(
            t["role"] == "assistant" and t["interrupted"] and t["text"] == "I'm holding Wednesday"
            for t in store.turns.values()
        )
    )


def test_stt_failure_sends_error_and_recovery_line(client: TestClient, stt: FakeSTT) -> None:
    stt.fail = True
    token = new_token(client)
    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        send_utterance(ws, 1, "hello", int(time.time() * 1000))
        events = receive_until(ws, "agent.text.done", turn_id=1)
    error = next(e for e in events if e["type"] == "error")
    assert error["code"] == "STT_FAILED" and error["retryable"] is True
    assert text_of(events, 1) == STT_RECOVERY_LINE


def test_llm_failure_sends_error_and_recovery_line(client: TestClient, llm: FakeLLM) -> None:
    llm.fail = True
    token = new_token(client)
    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        ws.send_json({"type": "text.message", "text": "hello", "ts": 1})
        events = receive_until(ws, "agent.text.done", turn_id=1)
    assert any(e["type"] == "error" and e["code"] == "LLM_FAILED" for e in events)


def test_call_limit_per_ip(
    client: TestClient, store: MemoryCallStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "calls_per_ip_per_day", 10)  # independent of local .env
    token = new_token(client)
    session_id = next(iter(store.sessions))
    for _ in range(10):
        store.calls[uuid.uuid4()] = {"session_id": session_id, "started_at": datetime.now(UTC)}
    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        ws.send_json({"type": "call.start"})
        event = ws.receive_json()
    assert event["code"] == "CALL_LIMIT_REACHED"


def test_expired_session_is_rejected(client: TestClient, store: MemoryCallStore) -> None:
    token = new_token(client)
    session = next(iter(store.sessions.values()))
    session["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        assert ws.receive_json()["code"] == "SESSION_EXPIRED"


def test_reconnect_resumes_the_same_call_with_history(client: TestClient, llm: FakeLLM) -> None:
    token = new_token(client)
    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        call_id = start_call(ws)[0]["call_id"]
        ws.send_json({"type": "text.message", "text": "My name is Juan", "ts": 1})
        receive_until(ws, "agent.text.done", turn_id=1)

    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        ws.send_json({"type": "call.start", "resume_call_id": call_id})
        events = receive_until(ws, "agent.text.done")
        assert events[0]["call_id"] == call_id
        assert RECONNECT_LINE in text_of(events, events[-1]["turn_id"])
        ws.send_json({"type": "text.message", "text": "So, about Friday", "ts": 2})
        receive_until(ws, "agent.text.done", turn_id=events[-1]["turn_id"] + 1)

    assert any(m.content == "My name is Juan" for m in llm.calls[-1])


def test_cannot_resume_another_sessions_call(client: TestClient) -> None:
    token_a, token_b = new_token(client), new_token(client)
    with client.websocket_connect(f"/ws/call?token={token_a}") as ws:
        call_a = start_call(ws)[0]["call_id"]
    with client.websocket_connect(f"/ws/call?token={token_b}") as ws:
        events = start_call(ws, resume_call_id=call_a)
    assert events[0]["call_id"] != call_a
    assert text_of(events, 0) == GREETING


def test_a_crashing_turn_still_answers_the_caller(client: TestClient, llm: FakeLLM) -> None:
    def broken(_: object) -> dict[str, object]:
        raise RuntimeError("bug")

    from app.providers.fake import ToolStep

    llm.replies = [ToolStep([("get_clinic_info", broken)])]
    token = new_token(client)
    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        ws.send_json({"type": "text.message", "text": "hello", "ts": 1})
        events = receive_until(ws, "agent.text.done", turn_id=1)
    assert any(e["type"] == "error" and e["code"] == "LLM_FAILED" for e in events)
    assert "Sorry" in text_of(events, 1)


def test_a_reply_stops_at_its_first_question(client: TestClient, llm: FakeLLM) -> None:
    llm.replies = ["Got it. Does 9:30 work for you?Yes, please. [Calling confirm_booking] Done."]
    token = new_token(client)
    with client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws)
        ws.send_json({"type": "text.message", "text": "Book me in", "ts": 1})
        events = receive_until(ws, "agent.text.done", turn_id=1)
    assert text_of(events, 1) == "Got it. Does 9:30 work for you?"
    assert [e["text"] for e in events if e["type"] == "agent.sentence"] == [
        "Got it.",
        "Does 9:30 work for you?",
    ]
    # The LLM's history holds only what was said.
    assert llm.calls and "Yes, please" not in str(llm.calls[-1])
