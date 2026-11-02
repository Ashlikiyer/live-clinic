import json
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.config import get_settings

router = APIRouter()


def now_ms() -> int:
    return int(time.time() * 1000)


def origin_allowed(origin: str | None, frontend_origin: str) -> bool:
    """Browsers always send Origin; non-browser clients (tests, scripts) may omit it."""
    return origin is None or origin.rstrip("/") == frontend_origin.rstrip("/")


@router.websocket("/ws/call")
async def call_socket(websocket: WebSocket) -> None:
    """Phase 0 echo route. Phase 1 replaces the body with a CallSession."""
    if not origin_allowed(websocket.headers.get("origin"), get_settings().frontend_origin):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                await websocket.send_json(
                    {"type": "echo", "ts": now_ms(), "bytes": len(message["bytes"])}
                )
            elif message.get("text") is not None:
                await websocket.send_json(_echo_text(message["text"]))
    except WebSocketDisconnect:
        pass


def _echo_text(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "type": "error",
            "ts": now_ms(),
            "code": "INVALID_MESSAGE",
            "message": "Expected a JSON event.",
            "retryable": False,
        }
    return {"type": "echo", "ts": now_ms(), "data": payload}
