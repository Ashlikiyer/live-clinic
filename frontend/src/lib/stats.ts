import type { CallStats } from "@/realtime/events";
import type { TurnMetric } from "@/store/reducer";

export function percentile(values: number[], p: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const rank = (p / 100) * (sorted.length - 1);
  const lo = Math.floor(rank);
  const hi = Math.ceil(rank);
  return Math.round(sorted[lo] + (sorted[hi] - sorted[lo]) * (rank - lo));
}

export function median(values: number[]): number | null {
  return percentile(values, 50);
}

export function callStats(metrics: TurnMetric[], durationS: number): CallStats {
  const totals = metrics.map((m) => m.totalMs);
  return {
    duration_s: Math.round(durationS),
    turn_count: metrics.length,
    median_reply_ms: median(totals),
    slowest_reply_ms: totals.length ? Math.max(...totals) : null,
  };
}
