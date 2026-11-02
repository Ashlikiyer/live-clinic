from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.db.session import check_database

router = APIRouter()

DatabaseCheck = Callable[[], Awaitable[bool]]


def get_database_check() -> DatabaseCheck:
    return check_database


@router.get("/api/health")
async def health(
    db_check: Annotated[DatabaseCheck, Depends(get_database_check)],
) -> JSONResponse:
    """Liveness plus a database check. Also used to wake the Render free tier."""
    db_ok = await db_check()
    return JSONResponse(
        {"status": "ok" if db_ok else "degraded", "database": "ok" if db_ok else "unavailable"},
        status_code=200 if db_ok else 503,
    )
