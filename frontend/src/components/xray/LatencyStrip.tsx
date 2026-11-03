"use client";

import { useState } from "react";

import { median } from "@/lib/stats";
import { formatMs } from "@/lib/time";
import { STAGE_KEYS } from "@/realtime/events";
import { useCallStore } from "@/store/callStore";

import { SEGMENT_META, type SegmentKey } from "./segments";
import { TurnBar } from "./TurnBar";

export const TARGET_MS = 1500;
const PLOT_HEIGHT_PX = 76;
const LEGEND_KEYS: SegmentKey[] = [
  "vad_wait_ms",
  "upload_ms",
  "stt_ms",
  "llm_ttft_ms",
  "tools",
  "first_sentence_ms",
  "tts_ms",
  "other",
];

export function LatencyStrip({ compact }: { compact: boolean }) {
  const metrics = useCallStore((s) => s.metrics);
  const [showTable, setShowTable] = useState(false);
  const last = metrics.at(-1);

  if (compact) {
    return (
      <div className="sticky bottom-0 flex justify-center border-t border-line bg-surface p-2">
        <span className="rounded-full bg-surface-muted px-3 py-1 text-xs tabular-nums text-ink-muted">
          {last ? `last reply: ${formatMs(last.totalMs)}${last.interrupted ? " ⚡" : ""}` : "last reply: —"}
        </span>
      </div>
    );
  }

  // Whole seconds on the scale, at least up to 3 s so the 1.5 s target always shows.
  const scaleMs = Math.max(3000, Math.ceil(Math.max(0, ...metrics.map((m) => m.totalMs)) / 1000) * 1000);
  const ticks = Array.from({ length: scaleMs / 1000 + 1 }, (_, i) => i * 1000);
  const med = median(metrics.map((m) => m.totalMs));

  return (
    <section aria-label="Latency X-ray" className="border-t border-line bg-surface px-4 py-3">
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        <h2 className="text-sm font-semibold">Latency X-ray</h2>
        <p className="text-xs tabular-nums text-ink-muted">
          {med === null
            ? "Each reply appears here, split by pipeline stage"
            : `median ${formatMs(med)} · target ${formatMs(TARGET_MS)}`}
        </p>
        <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink-muted" aria-label="Legend">
          {LEGEND_KEYS.map((key) => (
            <li key={key} className="flex items-center gap-1">
              <span
                aria-hidden
                className={`size-2.5 rounded-[2px] ${key === "tools" ? "hatched" : ""}`}
                style={{ backgroundColor: SEGMENT_META[key].color }}
              />
              {SEGMENT_META[key].label}
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={() => setShowTable((v) => !v)}
          aria-pressed={showTable}
          disabled={metrics.length === 0}
          className="ml-auto rounded-full border border-line px-3 py-0.5 text-xs text-ink-muted hover:bg-surface-muted disabled:opacity-50"
        >
          {showTable ? "Chart" : "Table"}
        </button>
      </div>

      {showTable ? (
        <XrayTable />
      ) : (
        <div className="mt-4 flex gap-2">
          {/* Y axis: whole seconds, hairline gridlines, and the 1.5 s target. */}
          <div className="relative w-7 shrink-0 text-right text-[10px] tabular-nums text-ink-muted" style={{ height: PLOT_HEIGHT_PX }}>
            {ticks.map((t) => (
              <span key={t} className="absolute right-0 -translate-y-1/2" style={{ bottom: (t / scaleMs) * PLOT_HEIGHT_PX }}>
                {t / 1000}s
              </span>
            ))}
          </div>
          <div className="relative min-w-0 flex-1">
            <div className="pointer-events-none absolute inset-x-0 top-0" style={{ height: PLOT_HEIGHT_PX }} aria-hidden>
              {ticks.map((t) => (
                <div key={t} className="absolute inset-x-0 border-t border-line" style={{ bottom: (t / scaleMs) * PLOT_HEIGHT_PX }} />
              ))}
              <div
                className="absolute inset-x-0 border-t border-ink-muted/60"
                style={{ bottom: (TARGET_MS / scaleMs) * PLOT_HEIGHT_PX }}
              >
                <span className="absolute -top-4 right-0 text-[10px] text-ink-muted">1.5 s target</span>
              </div>
            </div>
            <div className="relative flex items-end gap-1.5 overflow-x-auto pb-0.5" style={{ height: PLOT_HEIGHT_PX + 20 }}>
              {metrics.map((m) => (
                <TurnBar key={m.turnId} metric={m} scaleMs={scaleMs} heightPx={PLOT_HEIGHT_PX} />
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

/** Every value in the chart, readable without hovering or telling colors apart. */
function XrayTable() {
  const metrics = useCallStore((s) => s.metrics);
  return (
    <div className="max-h-40 overflow-auto">
      <table className="w-full text-left text-xs tabular-nums">
        <thead className="sticky top-0 bg-surface text-ink-muted">
          <tr>
            <th className="py-1 pr-3 font-medium">Reply</th>
            <th className="py-1 pr-3 font-medium">Total</th>
            {STAGE_KEYS.map((k) => (
              <th key={k} className="py-1 pr-3 font-medium">
                {SEGMENT_META[k].label}
              </th>
            ))}
            <th className="py-1 pr-3 font-medium">Tools</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((m) => (
            <tr key={m.turnId} className="border-t border-line">
              <td className="py-1 pr-3">
                {m.turnId}
                {m.interrupted && " ⚡"}
              </td>
              <td className="py-1 pr-3 font-semibold">{m.totalMs} ms</td>
              {STAGE_KEYS.map((k) => (
                <td key={k} className="py-1 pr-3">
                  {m.stages[k] ?? "—"}
                </td>
              ))}
              <td className="py-1 pr-3">{m.toolMs || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
