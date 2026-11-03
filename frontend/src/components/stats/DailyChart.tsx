"use client";

import { useState } from "react";

import { secondsTick, type StatsResponse } from "@/lib/statsView";
import { formatMs, formatShortDay } from "@/lib/time";

const W = 560;
const H = 200;
const PAD = { left: 40, right: 92, top: 12, bottom: 26 };

const SERIES = [
  { key: "median_total_ms", label: "Median", color: "var(--series-1)" },
  { key: "p95_total_ms", label: "p95", color: "var(--series-2)" },
] as const;

/** Two series on one ms axis: legend + direct end labels; crosshair tooltip snaps to the day. */
export function DailyChart({ daily }: { daily: StatsResponse["daily"] }) {
  const [active, setActive] = useState<number | null>(null);
  const values = daily.flatMap((d) => [d.median_total_ms, d.p95_total_ms]).filter((v): v is number => v !== null);
  const maxMs = Math.max(2000, Math.ceil(Math.max(0, ...values) / 1000) * 1000);
  const yTicks = Array.from({ length: maxMs / 1000 + 1 }, (_, i) => i * 1000);
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (daily.length > 1 ? (i / (daily.length - 1)) * plotW : plotW / 2);
  const y = (ms: number) => PAD.top + plotH - (ms / maxMs) * plotH;

  const path = (key: (typeof SERIES)[number]["key"]) => {
    let d = "";
    let pen = false;
    daily.forEach((day, i) => {
      const v = day[key];
      if (v === null) {
        pen = false; // a day without replies breaks the line rather than inventing a value
        return;
      }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
      pen = true;
    });
    return d;
  };
  const lastIndex = (key: (typeof SERIES)[number]["key"]) => daily.findLastIndex((d) => d[key] !== null);
  const shown = active === null ? null : daily[active];

  return (
    <div>
      <div className="mb-2 flex gap-4 text-xs text-ink-muted" aria-label="Legend">
        {SERIES.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span aria-hidden className="h-[2px] w-4 rounded-full" style={{ backgroundColor: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Daily median and p95 reply time">
          {yTicks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth={1} />
              <text x={PAD.left - 6} y={y(t) + 3} textAnchor="end" fontSize={13} fill="var(--ink-muted)">
                {secondsTick(t)}
              </text>
            </g>
          ))}
          {daily.map((d, i) => (
            <text key={d.day} x={x(i)} y={H - 6} textAnchor="middle" fontSize={13} fill="var(--ink-muted)">
              {formatShortDay(d.day)}
            </text>
          ))}
          {active !== null && (
            <line x1={x(active)} x2={x(active)} y1={PAD.top} y2={PAD.top + plotH} stroke="var(--ink-muted)" strokeWidth={1} />
          )}
          {SERIES.map((s) => (
            <g key={s.key}>
              <path d={path(s.key)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {daily.map((d, i) =>
                d[s.key] === null ? null : (
                  <circle key={d.day} cx={x(i)} cy={y(d[s.key] as number)} r={4} fill={s.color} stroke="var(--surface)" strokeWidth={2} />
                ),
              )}
              {lastIndex(s.key) >= 0 && (
                <text
                  x={x(lastIndex(s.key)) + 8}
                  y={y(daily[lastIndex(s.key)][s.key] as number) + 3}
                  fontSize={13}
                  fill="var(--ink)"
                >
                  {s.label} {formatMs(daily[lastIndex(s.key)][s.key] as number)}
                </text>
              )}
            </g>
          ))}
          {daily.map((d, i) => (
            // Hit target: the whole column around each day, not the 8px dot.
            <rect
              key={d.day}
              x={x(i) - plotW / Math.max(1, daily.length - 1) / 2}
              y={PAD.top}
              width={plotW / Math.max(1, daily.length - 1)}
              height={plotH}
              fill="transparent"
              tabIndex={0}
              aria-label={`${d.day}: median ${d.median_total_ms ?? "no data"} ms, p95 ${d.p95_total_ms ?? "no data"} ms, ${d.replies} replies`}
              onPointerEnter={() => setActive(i)}
              onPointerLeave={() => setActive(null)}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(null)}
            />
          ))}
        </svg>
      </div>
      <p className="mt-1 h-5 text-sm" aria-live="polite">
        {shown ? (
          shown.replies === 0 ? (
            <span className="text-ink-muted">{shown.day}: no replies</span>
          ) : (
            <>
              <span className="font-semibold tabular-nums">{formatMs(shown.median_total_ms ?? 0)}</span>
              <span className="text-ink-muted"> median · </span>
              <span className="font-semibold tabular-nums">{formatMs(shown.p95_total_ms ?? 0)}</span>
              <span className="text-ink-muted"> p95 · {shown.replies} replies on {shown.day}</span>
            </>
          )
        ) : (
          <span className="text-ink-muted">Hover or focus a day for its numbers.</span>
        )}
      </p>
    </div>
  );
}
