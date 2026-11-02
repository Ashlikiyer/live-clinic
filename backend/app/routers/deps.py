"""Shared request dependencies: the caller's sandbox session."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request

from app.call.session import ToolDeps
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.security import hash_token
from app.repositories.calls import CallStore, SessionInfo

SESSION_COOKIE = "session_token"


def get_store(request: Request) -> CallStore:
    store: CallStore = request.app.state.store
    return store


def get_tools(request: Request) -> ToolDeps | None:
    tools: ToolDeps | None = request.app.state.tools
    return tools


def session_token(request: Request) -> str | None:
    """Bearer token (what the frontend sends), else the httpOnly cookie."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.cookies.get(SESSION_COOKIE)


async def require_session(
    request: Request, store: Annotated[CallStore, Depends(get_store)]
) -> SessionInfo:
    token = session_token(request)
    session = (
        await store.find_session(hash_token(get_settings().session_secret, token))
        if token
        else None
    )
    if session is None or session.expires_at <= datetime.now(UTC):
        raise AppError(
            ErrorCode.SESSION_EXPIRED, "Your demo session has expired. Start a new one.", 401
        )
    return session


CurrentSession = Annotated[SessionInfo, Depends(require_session)]
Store = Annotated[CallStore, Depends(get_store)]
Tools = Annotated[ToolDeps | None, Depends(get_tools)]
