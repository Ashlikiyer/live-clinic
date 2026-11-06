"""Public latency stats (no transcripts) and the daily cleanup job."""

import hmac
from datetime import datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, Request

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.repositories.stats import DayStats, StatsRepository
from app.stats.latency import percentile, summarize

router = APIRouter()

WINDOW_DAYS = 7


def _repo(request: Request) -> StatsRepository:
    repo: StatsRepository | None = request.app.state.stats
    if repo is None:
        raise AppError(ErrorCode.INTERNAL_ERROR, "Stats are unavailable.", 503)
    return repo


@router.get("/api/stats")
async def stats(request: Request) -> dict[str, Any]:
    """Last 7 days of reply latency across all calls. Aggregates only: no transcripts."""
    tz = ZoneInfo(get_settings().clinic_timezone)
    now = datetime.now(tz)
    first_day = now.date() - timedelta(days=WINDOW_DAYS - 1)
    since = datetime.combine(first_day, datetime.min.time(), tzinfo=tz)
    days = await _repo(request).window(first_day, since)

    overall = DayStats()
    for day_stats in days.values():
        overall.merge(day_stats)
    daily = []
    for offset in range(WINDOW_DAYS):
        day = first_day + timedelta(days=offset)
        d = days.get(day, DayStats())
        totals = d.rollup.histograms.get("total_ms", {})
        daily.append(
            {
                "day": day.isoformat(),
                "calls": d.call_count,
                "replies": d.rollup.turn_count,
                "median_total_ms": percentile(totals, 50),
                "p95_total_ms": percentile(totals, 95),
            }
        )
    return {
        "window_days": WINDOW_DAYS,
        "calls": overall.call_count,
        "outcomes": overall.outcomes,
        **summarize(overall.rollup),
        "daily": daily,
    }


@router.post("/api/internal/cleanup")
async def cleanup(
    request: Request, x_cron_secret: Annotated[str | None, Header()] = None
) -> dict[str, int]:
    """Daily job: roll expired sessions into daily_stats, delete them, and top up the seeded
    schedule when it no longer covers the booking window."""
    expected = get_settings().cron_secret
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, expected):
        raise AppError(ErrorCode.UNAUTHORIZED, "Bad cron secret.", 401)
    now = datetime.now(ZoneInfo(get_settings().clinic_timezone))
    repo = _repo(request)
    result = await repo.cleanup(now)
    reseeded = await repo.refresh_seed_if_stale(now)
    return {
        "deleted_sessions": result.deleted_sessions,
        "rolled_up_calls": result.rolled_up_calls,
        "rolled_up_turns": result.rolled_up_turns,
        "reseeded": int(reseeded),
    }
