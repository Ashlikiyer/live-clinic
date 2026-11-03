"""Queries for /api/stats and the daily cleanup. The arithmetic lives in app/stats/latency.py."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.call.metrics import STAGE_KEYS
from app.db.models import Call, DailyStats, SandboxSession, Turn, TurnMetrics
from app.stats.latency import Rollup, TurnSample, percentile


@dataclass
class DayStats:
    rollup: Rollup = field(default_factory=Rollup)
    call_count: int = 0
    outcomes: dict[str, int] = field(default_factory=dict)

    def merge(self, other: "DayStats") -> None:
        self.rollup.merge(other.rollup)
        self.call_count += other.call_count
        for outcome, count in other.outcomes.items():
            self.outcomes[outcome] = self.outcomes.get(outcome, 0) + count


@dataclass(frozen=True)
class CleanupResult:
    deleted_sessions: int
    rolled_up_turns: int
    rolled_up_calls: int


class StatsRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], tz: ZoneInfo) -> None:
        self._sessionmaker = sessionmaker
        self._tz = tz

    async def window(self, first_day: date, since: datetime) -> dict[date, DayStats]:
        """Per day: the daily rollups plus the not-yet-cleaned live rows since `since`."""
        days: dict[date, DayStats] = defaultdict(DayStats)
        async with self._sessionmaker() as db:
            for row in await db.scalars(select(DailyStats).where(DailyStats.day >= first_day)):
                days[row.day].merge(self._from_row(row))
            live = await self._live(db, since=since)
        for day, stats in live.items():
            days[day].merge(stats)
        return dict(days)

    async def cleanup(self, now: datetime) -> CleanupResult:
        """Roll expired sessions into daily_stats, then delete them (cascades to their data)."""
        async with self._sessionmaker() as db, db.begin():
            expired = select(SandboxSession.id).where(SandboxSession.expires_at < now)
            per_day = await self._live(db, session_ids=expired)
            for day, stats in per_day.items():
                row = await db.get(DailyStats, day, with_for_update=True)
                if row is None:
                    row = DailyStats(day=day, histograms={}, slow_causes={}, outcomes={})
                    db.add(row)
                merged = self._from_row(row)
                merged.merge(stats)
                self._write_row(row, merged)
            result = await db.execute(delete(SandboxSession).where(SandboxSession.expires_at < now))
            deleted = int(getattr(result, "rowcount", 0) or 0)
        return CleanupResult(
            deleted_sessions=deleted,
            rolled_up_turns=sum(s.rollup.turn_count for s in per_day.values()),
            rolled_up_calls=sum(s.call_count for s in per_day.values()),
        )

    # ---------- helpers ----------

    async def _live(
        self,
        db: AsyncSession,
        *,
        since: datetime | None = None,
        session_ids: Any = None,
    ) -> dict[date, DayStats]:
        """Live per-turn metrics and calls, grouped by clinic-time day."""
        days: dict[date, DayStats] = defaultdict(DayStats)

        turns = (
            select(Turn.created_at, Turn.interrupted, TurnMetrics)
            .join(TurnMetrics, TurnMetrics.turn_id == Turn.id)
            .join(Call, Call.id == Turn.call_id)
        )
        calls = select(Call.started_at, Call.outcome)
        if since is not None:
            turns = turns.where(Turn.created_at >= since)
            calls = calls.where(Call.started_at >= since)
        if session_ids is not None:
            turns = turns.where(Call.session_id.in_(session_ids))
            calls = calls.where(Call.session_id.in_(session_ids))

        for created_at, interrupted, m in (await db.execute(turns)).all():
            if m.total_ms is None:
                continue
            sample = TurnSample(
                stages={key: getattr(m, key) for key in STAGE_KEYS},
                total_ms=m.total_ms,
                interrupted=interrupted,
                stop_ms=m.stop_ms,
            )
            days[created_at.astimezone(self._tz).date()].rollup.add(sample)

        for started_at, outcome in (await db.execute(calls)).all():
            day = days[started_at.astimezone(self._tz).date()]
            day.call_count += 1
            if outcome:
                day.outcomes[outcome] = day.outcomes.get(outcome, 0) + 1
        return days

    @staticmethod
    def _from_row(row: DailyStats) -> DayStats:
        return DayStats(
            rollup=Rollup(
                turn_count=row.turn_count or 0,
                interruption_count=row.interruption_count or 0,
                histograms={k: dict(v) for k, v in (row.histograms or {}).items()},
                slow_causes=dict(row.slow_causes or {}),
            ),
            call_count=row.call_count or 0,
            outcomes=dict(row.outcomes or {}),
        )

    @staticmethod
    def _write_row(row: DailyStats, stats: DayStats) -> None:
        r = stats.rollup
        row.call_count = stats.call_count
        row.turn_count = r.turn_count
        row.interruption_count = r.interruption_count
        row.histograms = r.histograms
        row.slow_causes = r.slow_causes
        row.outcomes = stats.outcomes
        totals = r.histograms.get("total_ms", {})
        row.median_total_ms = percentile(totals, 50)
        row.p95_total_ms = percentile(totals, 95)
        row.stage_medians = {k: percentile(r.histograms.get(k, {}), 50) for k in STAGE_KEYS}
