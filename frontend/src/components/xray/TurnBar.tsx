"use client";

import { motion } from "motion/react";
import { useRef, useState } from "react";

import { formatMs } from "@/lib/time";
import type { TurnMetric } from "@/store/reducer";

import { turnSegments } from "./segments";

/** Column width cap and the surface gap between stacked segments (dataviz mark specs). */
const BAR_WIDTH_PX = 22;
const GAP_PX = 2;

export function TurnBar({
  metric,
  scaleMs,
  heightPx,
}: {
  metric: TurnMetric;
  scaleMs: number;
  heightPx: number;
}) {
  // The bar row scrolls sideways, which clips anything overflowing it, so the tooltip is
  // positioned against the viewport from the bar's measured position instead.
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const open = anchor !== null;
  const show = () => {
    const r = ref.current?.getBoundingClientRect();
    if (r) setAnchor({ x: r.left + r.width / 2, y: r.top });
  };
  const hide = () => setAnchor(null);
  const segments = turnSegments(metric);
  const barHeight = Math.max(4, (metric.totalMs / scaleMs) * heightPx);
  const label = `Reply ${metric.turnId}: ${formatMs(metric.totalMs)}${
    metric.interrupted ? ", interrupted" : ""
  }. ${segments.map((s) => `${s.label} ${Math.round(s.ms)} ms`).join(", ")}`;

  return (
    <div
      className="relative flex h-full w-9 shrink-0 flex-col items-center justify-end outline-none"
      tabIndex={0}
      role="img"
      aria-label={label}
      ref={ref}
      onPointerEnter={show}
      onPointerLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <motion.div
        className={`flex flex-col-reverse overflow-hidden rounded-t-[4px] transition-[filter] ${
          open ? "brightness-110" : ""
        }`}
        style={{ width: BAR_WIDTH_PX, gap: GAP_PX }}
        initial={{ height: 0 }}
        animate={{ height: barHeight }}
        transition={{ duration: 0.3 }}
      >
        {segments.map((s) => (
          <div
            key={s.key}
            className={`shrink-0 ${s.hatched ? "hatched" : ""}`}
            style={{
              // Each segment keeps its share of the bar after the 2px gaps are taken out.
              flexBasis: `calc(${(s.ms / metric.totalMs) * 100}% - ${GAP_PX}px)`,
              minHeight: 1,
              backgroundColor: s.color,
            }}
          />
        ))}
      </motion.div>
      <span className="mt-1 h-4 text-[10px] tabular-nums text-ink-muted">
        {metric.interrupted && <span aria-hidden>⚡</span>}
        {(metric.totalMs / 1000).toFixed(1)}
      </span>

      {anchor && (
        <div
          role="tooltip"
          className="pointer-events-none fixed z-50 w-56 -translate-x-1/2 -translate-y-full rounded-xl border border-line bg-surface p-3 text-xs shadow-lg"
          style={{ left: Math.max(120, anchor.x), top: anchor.y - 8 }}
        >
          <p className="flex items-baseline justify-between gap-2">
            <span className="text-base font-semibold tabular-nums text-ink">
              {formatMs(metric.totalMs)}
            </span>
            <span className="text-ink-muted">
              Reply {metric.turnId}
              {metric.interrupted && " · ⚡ interrupted"}
            </span>
          </p>
          <ul className="mt-2 space-y-1">
            {segments.map((s) => (
              <li key={s.key} className="flex items-center gap-2">
                <span
                  aria-hidden
                  className={`h-[3px] w-3 rounded-full ${s.hatched ? "hatched" : ""}`}
                  style={{ backgroundColor: s.color }}
                />
                <span className="flex-1 text-ink-muted">{s.label}</span>
                <span className="font-medium tabular-nums text-ink">{Math.round(s.ms)} ms</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
