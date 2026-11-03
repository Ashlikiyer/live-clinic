/** Shapes GET /api/stats into chart-ready data. Pure, no I/O. */

import { STAGE_KEYS, type CallOutcome, type StageKey } from "@/realtime/events";

export interface StatsResponse {
  window_days: number;
  calls: number;
  outcomes: Partial<Record<CallOutcome, number>>;
  replies: number;
  median_total_ms: number | null;
  p95_total_ms: number | null;
  stage_medians: Record<StageKey, number | null>;
  slow_turn_threshold_ms: number;
  slow_turn_share: number | null;
  slow_turn_causes: Partial<Record<StageKey, number>>;
  interruptions: number;
  avg_stop_ms: number | null;
  histogram_bucket_ms: number;
  total_ms_histogram: Record<string, number>;
  daily: {
    day: string;
    calls: number;
    replies: number;
    median_total_ms: number | null;
    p95_total_ms: number | null;
  }[];
}

export interface Bin {
  startMs: number;
  endMs: number;
  count: number;
  /** The last bin of a capped axis: everything from startMs up. */
  open?: boolean;
}

/**
 * Re-bin the server's 50 ms histogram into display bins of `widthMs`, from 0 to the last
 * non-empty bin, with empty bins kept so the x-axis stays continuous.
 */
export function rebin(hist: Record<string, number>, widthMs: number, capMs = Infinity): Bin[] {
  const entries = Object.entries(hist).map(([k, v]) => [Number(k), v] as const);
  if (entries.length === 0) return [];
  const last = Math.min(Math.max(...entries.map(([k]) => k)), capMs);
  const bins: Bin[] = [];
  for (let start = 0; start <= last; start += widthMs) {
    bins.push({ startMs: start, endMs: start + widthMs, count: 0 });
  }
  // Rare slow outliers share one "cap+" bin instead of squeezing the whole axis.
  if (Number.isFinite(capMs) && last >= capMs) bins[bins.length - 1].open = true;
  for (const [k, v] of entries) bins[Math.min(Math.floor(k / widthMs), bins.length - 1)].count += v;
  return bins;
}

export interface StagePart {
  key: StageKey;
  ms: number;
  share: number;
}

/** Median of each stage as a share of their sum: "where a typical reply's time goes". */
export function stageBreakdown(medians: Record<StageKey, number | null>): StagePart[] {
  const parts = STAGE_KEYS.map((key) => ({ key, ms: medians[key] ?? 0 })).filter((p) => p.ms > 0);
  const sum = parts.reduce((a, p) => a + p.ms, 0);
  return parts.map((p) => ({ ...p, share: sum ? p.ms / sum : 0 }));
}

/** Slow-reply causes, largest first. */
export function rankedCauses(causes: Partial<Record<StageKey, number>>): { key: StageKey; count: number }[] {
  return STAGE_KEYS.filter((k) => (causes[k] ?? 0) > 0)
    .map((key) => ({ key, count: causes[key] ?? 0 }))
    .sort((a, b) => b.count - a.count);
}

/** "0.4 s" style tick for an axis (clean, compact). */
export function secondsTick(ms: number): string {
  const s = ms / 1000;
  return `${Number.isInteger(s) ? s : s.toFixed(1)} s`;
}
