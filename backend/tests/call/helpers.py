import time
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from app.providers.fake import fake_wav
from app.schemas.events import build_audio_frame

Event = dict[str, Any]


def new_token(client: TestClient) -> str:
    response = client.post("/api/sessions")
    assert response.status_code == 201, response.text
    token: str = response.json()["session_token"]
    return token


def receive_until(
    ws: WebSocketTestSession, type_: str, *, turn_id: int | None = None, limit: int = 200
) -> list[Event]:
    """Collect events up to and including the first `type_` (for `turn_id`, if given)."""
    events: list[Event] = []
    for _ in range(limit):
        event: Event = ws.receive_json()
        events.append(event)
        if event["type"] == type_ and (turn_id is None or event.get("turn_id") == turn_id):
            return events
    raise AssertionError(f"No {type_} event; got {[e['type'] for e in events]}")


def start_call(ws: WebSocketTestSession, **extra: Any) -> list[Event]:
    ws.send_json({"type": "call.start", "voice": "kokoro", "ts": int(time.time() * 1000), **extra})
    return receive_until(ws, "agent.text.done", turn_id=0)


def send_utterance(ws: WebSocketTestSession, turn_id: int, text: str, speech_end_ts: int) -> None:
    header = {
        "type": "audio.utterance",
        "turn_id": turn_id,
        "speech_end_ts": speech_end_ts,
        "vad_wait_ms": 600,
    }
    ws.send_bytes(build_audio_frame(header, fake_wav(text)))


def text_of(events: list[Event], turn_id: int) -> str:
    return "".join(
        e["delta"] for e in events if e["type"] == "agent.text.delta" and e["turn_id"] == turn_id
    )


def wait_for(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    """Background database writes finish shortly after the events; poll for them."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("Condition not met in time")
