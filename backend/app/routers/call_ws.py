from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, status

from app.call.session import CallSession
from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.core.security import hash_token
from app.repositories.calls import CallStore
from app.routers.sessions import SESSION_COOKIE
from app.schemas.events import server_event

router = APIRouter()


def origin_allowed(origin: str | None, frontend_origin: str) -> bool:
    """Browsers always send Origin; non-browser clients (tests, scripts) may omit it."""
    return origin is None or origin.rstrip("/") == frontend_origin.rstrip("/")


@router.websocket("/ws/call")
async def call_socket(websocket: WebSocket) -> None:
    """One live call. See the WebSocket event protocol in the spec."""
    settings = get_settings()
    if not origin_allowed(websocket.headers.get("origin"), settings.frontend_origin):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    store: CallStore = websocket.app.state.store
    token = websocket.query_params.get("token") or websocket.cookies.get(SESSION_COOKIE)
    session = (
        await store.find_session(hash_token(settings.session_secret, token)) if token else None
    )
    if session is None or session.expires_at <= datetime.now(UTC):
        await websocket.send_json(
            server_event(
                "error",
                code=ErrorCode.SESSION_EXPIRED.value,
                message="Your demo session has expired. Please start a new call.",
                retryable=False,
            )
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await CallSession(websocket, session, store, websocket.app.state.providers, settings).run()
