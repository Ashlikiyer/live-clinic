from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.call.busy import line_is_busy
from app.db.session import check_database
from app.providers.base import busy_seconds

router = APIRouter()

DatabaseCheck = Callable[[], Awaitable[bool]]


def get_database_check() -> DatabaseCheck:
    return check_database


@router.get("/api/health")
async def health(
    request: Request,
    db_check: Annotated[DatabaseCheck, Depends(get_database_check)],
) -> JSONResponse:
    """Liveness plus a database check. Also used to wake the Render free tier, and tells the
    landing page whether Mia's line is busy (every Groq model rate limited)."""
    db_ok = await db_check()
    providers = getattr(request.app.state, "providers", None)
    wait = busy_seconds(providers.llm) if providers else 0.0
    busy = line_is_busy(wait)
    return JSONResponse(
        {
            "status": "ok" if db_ok else "degraded",
            "database": "ok" if db_ok else "unavailable",
            "llm": "busy" if busy else "ok",
            "busy_seconds": round(wait) if busy else 0,
        },
        status_code=200 if db_ok else 503,
    )
