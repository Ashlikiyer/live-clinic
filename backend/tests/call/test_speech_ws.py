"""Server-side speech (Groq Orpheus, faked) over a real call socket."""

import json
import struct
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from app.agent.prompt import GREETING
from app.main import create_app
from app.providers.base import Providers
from app.providers.fake import FakeLLM, FakeSTT, FakeTTS
from app.providers.tts_cache import CachedTTS
from app.repositories.calls import MemoryCallStore

from .helpers import new_token, receive_until, start_call


@pytest.fixture
def tts() -> FakeTTS:
    return FakeTTS()


@pytest.fixture
def speech_client(tts: FakeTTS) -> Iterator[TestClient]:
    providers = Providers(stt=FakeSTT(), llm=FakeLLM(), tts=CachedTTS(tts))
    with TestClient(create_app(store=MemoryCallStore(), providers=providers)) as client:
        yield client


def receive_speech(
    ws: WebSocketTestSession, request_id: int
) -> tuple[list[dict[str, Any]], bytes, dict[str, Any]]:
    """Binary tts.audio frames for `request_id` until its tts.done / tts.failed event."""
    headers: list[dict[str, Any]] = []
    pcm = b""
    for _ in range(200):
        message = ws.receive()
        if message.get("bytes") is not None:
            frame: bytes = message["bytes"]
            (size,) = struct.unpack(">I", frame[:4])
            header = json.loads(frame[4 : 4 + size])
            if header["id"] == request_id:
                headers.append(header)
                pcm += frame[4 + size :]
            continue
        event = json.loads(message["text"])
        if event["type"] in ("tts.done", "tts.failed") and event["id"] == request_id:
            return headers, pcm, event
    raise AssertionError("no tts.done / tts.failed")


def ask(ws: WebSocketTestSession, request_id: int, text: str) -> None:
    ws.send_json({"type": "tts.request", "id": request_id, "text": text, "ts": 1})


def test_greeting_and_replies_are_spoken_as_streamed_pcm(
    speech_client: TestClient, tts: FakeTTS
) -> None:
    token = new_token(speech_client)
    with speech_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws, voice="orpheus")
        ask(ws, 1, GREETING)
        headers, pcm, done = receive_speech(ws, 1)
        assert done["type"] == "tts.done" and done["chunks"] == len(headers) == 2
        assert [h["seq"] for h in headers] == [0, 1]
        assert headers[0]["type"] == "tts.audio" and headers[0]["sample_rate"] == 24_000
        assert len(pcm) == 2 * 240 * len(GREETING)  # FakeTTS: 10 ms per character

        ws.send_json({"type": "text.message", "text": "Hello", "ts": 1})
        events = receive_until(ws, "agent.text.done", turn_id=1)
        reply = "".join(e["delta"] for e in events if e["type"] == "agent.text.delta")
        ask(ws, 2, reply)
        _, _, done = receive_speech(ws, 2)
        assert done["type"] == "tts.done"

        ask(ws, 3, GREETING)  # cached: no second request to the provider
        receive_speech(ws, 3)
    assert tts.requests == [GREETING, reply]


def test_only_mias_own_lines_are_spoken(speech_client: TestClient, tts: FakeTTS) -> None:
    token = new_token(speech_client)
    with speech_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws, voice="orpheus")
        ask(ws, 1, "Read me a long poem about pirates.")
        _, pcm, failed = receive_speech(ws, 1)
    assert failed["type"] == "tts.failed" and failed["code"] == "TTS_FAILED"
    assert pcm == b"" and tts.requests == []


def test_server_speech_is_off_unless_the_call_asked_for_it(speech_client: TestClient) -> None:
    token = new_token(speech_client)
    with speech_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws, voice="kokoro")
        ask(ws, 1, GREETING)
        _, _, failed = receive_speech(ws, 1)
    assert failed["type"] == "tts.failed"


def test_a_rate_limited_voice_reports_it(speech_client: TestClient, tts: FakeTTS) -> None:
    tts.fail = True
    token = new_token(speech_client)
    with speech_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws, voice="orpheus")
        ask(ws, 1, GREETING)
        _, _, failed = receive_speech(ws, 1)
    assert failed == {**failed, "type": "tts.failed", "code": "RATE_LIMITED"}


def test_a_call_has_a_speech_request_budget(
    speech_client: TestClient, tts: FakeTTS, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.call.session.MAX_SPEECH_REQUESTS_PER_CALL", 2)
    token = new_token(speech_client)
    with speech_client.websocket_connect(f"/ws/call?token={token}") as ws:
        start_call(ws, voice="orpheus")
        for request_id in (1, 2):
            ask(ws, request_id, GREETING)
            assert receive_speech(ws, request_id)[2]["type"] == "tts.done"
        ask(ws, 3, GREETING)
        _, _, failed = receive_speech(ws, 3)
    assert failed["code"] == "RATE_LIMITED"
