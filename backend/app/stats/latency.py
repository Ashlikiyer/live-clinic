"""Latency statistics for the Latency X-ray and the /stats page. Pure functions, no I/O.

Everything is computed from 50 ms histograms, so per-turn rows (deleted after 24 h) and the
daily rollups that replace them combine exactly the same way: medians and p95 stay accurate to
one bucket across any number of days.
"""

import math
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.call.metrics import STAGE_KEYS

BUCKET_MS = 50
SLOW_TURN_MS = 2000

Histogram = dict[str, int]  # bucket start (ms, as a string for JSON) -> count


@dataclass(frozen=True)
class TurnSample:
    """One measured agent reply."""

    stages: Mapping[str, int | None]
    total_ms: int
    interrupted: bool = False
    stop_ms: int | None = None


@dataclass
class Rollup:
    """Aggregated replies: one day in daily_stats, or a whole window."""

    turn_count: int = 0
    interruption_count: int = 0
    # "total_ms", each stage key, and "stop_ms" -> histogram
    histograms: dict[str, Histogram] = field(default_factory=dict)
    # For replies over SLOW_TURN_MS: their slowest stage -> count
    slow_causes: dict[str, int] = field(default_factory=dict)

    def add(self, sample: TurnSample) -> None:
        self.turn_count += 1
        self.interruption_count += int(sample.interrupted)
        _bump(self.histograms.setdefault("total_ms", {}), sample.total_ms)
        for key in STAGE_KEYS:
            value = sample.stages.get(key)
            if value is not None:
                _bump(self.histograms.setdefault(key, {}), value)
        if sample.stop_ms is not None:
            _bump(self.histograms.setdefault("stop_ms", {}), sample.stop_ms)
        if sample.total_ms > SLOW_TURN_MS and (cause := slowest_stage(sample.stages)):
            self.slow_causes[cause] = self.slow_causes.get(cause, 0) + 1

    def merge(self, other: "Rollup") -> None:
        self.turn_count += other.turn_count
        self.interruption_count += other.interruption_count
        for key, hist in other.histograms.items():
            mine = self.histograms.setdefault(key, {})
            for bucket, count in hist.items():
                mine[bucket] = mine.get(bucket, 0) + count
        for cause, count in other.slow_causes.items():
            self.slow_causes[cause] = self.slow_causes.get(cause, 0) + count


def _bump(hist: Histogram, value_ms: int) -> None:
    bucket = str(max(0, int(value_ms)) // BUCKET_MS * BUCKET_MS)
    hist[bucket] = hist.get(bucket, 0) + 1


def slowest_stage(stages: Mapping[str, int | None]) -> str | None:
    measured = {k: v for k, v in stages.items() if k in STAGE_KEYS and v is not None}
    return max(measured, key=lambda k: measured[k]) if measured else None


def rollup(samples: Iterable[TurnSample]) -> Rollup:
    result = Rollup()
    for sample in samples:
        result.add(sample)
    return result


def percentile(hist: Histogram, p: float) -> int | None:
    """The p-th percentile (0-100), as the middle of the bucket it falls in."""
    total = sum(hist.values())
    if total == 0:
        return None
    rank = max(1, math.ceil(p / 100 * total))  # nearest-rank method
    seen = 0
    for bucket in sorted(hist, key=int):
        seen += hist[bucket]
        if seen >= rank:
            return int(bucket) + BUCKET_MS // 2
    return None  # unreachable


def mean(hist: Histogram) -> int | None:
    total = sum(hist.values())
    if total == 0:
        return None
    return round(sum((int(b) + BUCKET_MS / 2) * c for b, c in hist.items()) / total)


def slow_share(hist: Histogram) -> float | None:
    total = sum(hist.values())
    if total == 0:
        return None
    slow = sum(c for b, c in hist.items() if int(b) >= SLOW_TURN_MS)
    return round(slow / total, 3)


def summarize(window: Rollup) -> dict[str, Any]:
    """The numbers the /stats page and the call summary show."""
    totals = window.histograms.get("total_ms", {})
    return {
        "replies": window.turn_count,
        "median_total_ms": percentile(totals, 50),
        "p95_total_ms": percentile(totals, 95),
        "stage_medians": {
            key: percentile(window.histograms.get(key, {}), 50) for key in STAGE_KEYS
        },
        "slow_turn_threshold_ms": SLOW_TURN_MS,
        "slow_turn_share": slow_share(totals),
        "slow_turn_causes": dict(Counter(window.slow_causes).most_common()),
        "interruptions": window.interruption_count,
        "avg_stop_ms": mean(window.histograms.get("stop_ms", {})),
        "histogram_bucket_ms": BUCKET_MS,
        "total_ms_histogram": dict(sorted(totals.items(), key=lambda kv: int(kv[0]))),
    }
