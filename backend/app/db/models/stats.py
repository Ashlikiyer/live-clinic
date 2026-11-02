from datetime import date
from typing import Any

from sqlalchemy import Date
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DailyStats(Base):
    """Aggregate latency rollup kept after per-session data is deleted."""

    __tablename__ = "daily_stats"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    call_count: Mapped[int] = mapped_column(default=0)
    turn_count: Mapped[int] = mapped_column(default=0)
    interruption_count: Mapped[int] = mapped_column(default=0)
    median_total_ms: Mapped[int | None]
    p95_total_ms: Mapped[int | None]
    # {"vad_wait_ms": 600, "stt_ms": 310, ...}
    stage_medians: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    outcomes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
