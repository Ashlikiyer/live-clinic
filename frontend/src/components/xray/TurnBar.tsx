"use client";

import { motion } from "motion/react";

import { formatMs } from "@/lib/time";
import type { TurnMetric } from "@/store/reducer";

import { turnSegments } from "./segments";

const BAR_PX = 76;

export function TurnBar({ metric, scaleMs }: { metric: TurnMetric; scaleMs: number }) {
  const segments = turnSegments(metric);
  const tooltip = [
    `Turn ${metric.turnId}: ${formatMs(metric.totalMs)}${metric.interrupted ? " (interrupted)" : ""}`,
    ...segments.map((s) => `${s.label}: ${Math.round(s.ms)} ms`),
  ].join("\n");

  return (
    <div className="group relative flex w-9 shrink-0 flex-col items-center" title={tooltip}>
      <motion.div
        className="flex w-full flex-col-reverse overflow-hidden rounded-md"
        initial={{ height: 0 }}
        animate={{ height: (metric.totalMs / scaleMs) * BAR_PX }}
        transition={{ duration: 0.3 }}
        role="img"
        aria-label={tooltip}
      >
        {segments.map((s) => (
          <div
            key={s.key}
            className={s.hatched ? "hatched" : undefined}
            style={{ height: `${(s.ms / metric.totalMs) * 100}%`, backgroundColor: s.color }}
          />
        ))}
      </motion.div>
      <span className="absolute -bottom-5 text-[10px] tabular-nums text-ink-muted">
        {metric.interrupted && <span aria-label="interrupted">⚡</span>}
        {(metric.totalMs / 1000).toFixed(1)}
      </span>
    </div>
  );
}
