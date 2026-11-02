import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.routers.call_ws import origin_allowed


def test_echoes_json_events(client: TestClient) -> None:
    with client.websocket_connect("/ws/call?token=test") as ws:
        ws.send_json({"type": "ping"})
        reply = ws.receive_json()
    assert reply["type"] == "echo"
    assert reply["data"] == {"type": "ping"}
    assert isinstance(reply["ts"], int)


def test_reports_binary_frame_size(client: TestClient) -> None:
    with client.websocket_connect("/ws/call") as ws:
        ws.send_bytes(b"\x00" * 128)
        assert ws.receive_json()["bytes"] == 128


def test_invalid_json_returns_error_event(client: TestClient) -> None:
    with client.websocket_connect("/ws/call") as ws:
        ws.send_text("not json")
        reply = ws.receive_json()
    assert reply["type"] == "error"
    assert reply["retryable"] is False


def test_rejects_foreign_origin(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/call", headers={"origin": "https://evil.example"}):
            pass
    assert exc.value.code == 1008


@pytest.mark.parametrize(
    ("origin", "allowed"),
    [
        (None, True),
        ("http://localhost:3000", True),
        ("http://localhost:3000/", True),
        ("http://localhost:3001", False),
    ],
)
def test_origin_allowed(origin: str | None, allowed: bool) -> None:
    assert origin_allowed(origin, "http://localhost:3000") is allowed
