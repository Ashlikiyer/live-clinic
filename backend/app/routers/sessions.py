import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.security import client_ip, hash_ip, hash_token, new_token
from app.repositories.calls import CallStore

router = APIRouter()

SESSION_TTL = timedelta(hours=24)
SESSION_COOKIE = "session_token"


class SessionCreated(BaseModel):
    session_token: str
    expires_at: datetime


def get_store(request: Request) -> CallStore:
    store: CallStore = request.app.state.store
    return store


@router.post("/api/sessions", status_code=201)
async def create_session(request: Request, response: Response) -> SessionCreated:
    """Create a personal sandbox for this visitor. Rate limited per IP."""
    settings = get_settings()
    store = get_store(request)
    ip_hash = hash_ip(settings.session_secret, client_ip(request))
    since = datetime.now(UTC) - timedelta(days=1)
    if await store.count_sessions_since(ip_hash, since) >= settings.sessions_per_ip_per_day:
        raise AppError(
            ErrorCode.RATE_LIMITED, "Too many sessions today. Please try again later.", 429
        )

    token = new_token()
    expires_at = datetime.now(UTC) + SESSION_TTL
    await store.create_session(
        uuid.uuid4(), hash_token(settings.session_secret, token), ip_hash, expires_at
    )
    secure = request.url.scheme == "https"
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=secure,
        samesite="none" if secure else "lax",
    )
    return SessionCreated(session_token=token, expires_at=expires_at)
