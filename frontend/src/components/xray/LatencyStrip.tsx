"use client";

import { median } from "@/lib/stats";
import { formatMs } from "@/lib/time";
import { useCallStore } from "@/store/callStore";

import { SEGMENT_META, type SegmentKey } from "./segments";
import { TurnBar } from "./TurnBar";

export const TARGET_MS = 1500;
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

  const scaleMs = Math.max(2500, ...metrics.map((m) => m.totalMs));
  const med = median(metrics.map((m) => m.totalMs));

  return (
    <section aria-label="Latency X-ray" className="border-t border-line bg-surface px-4 py-3">
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        <h2 className="text-sm font-semibold">Latency X-ray</h2>
        <p className="text-xs tabular-nums text-ink-muted">
          {med === null ? "No replies yet" : `median ${formatMs(med)} · target ${formatMs(TARGET_MS)}`}
        </p>
        <ul className="ml-auto flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink-muted">
          {LEGEND_KEYS.map((key) => (
            <li key={key} className="flex items-center gap-1">
              <span
                className={`size-2.5 rounded-sm ${key === "tools" ? "hatched" : ""}`}
                style={{ backgroundColor: SEGMENT_META[key].color }}
              />
              {SEGMENT_META[key].label}
            </li>
          ))}
        </ul>
      </div>
      <div className="relative flex h-24 items-end gap-1.5 overflow-x-auto pb-5">
        <div
          className="pointer-events-none absolute inset-x-0 border-t border-dashed border-danger/60"
          style={{ bottom: `calc(1.25rem + ${(TARGET_MS / scaleMs) * 76}px)` }}
          aria-hidden
        />
        {metrics.length === 0 && (
          <p className="w-full self-center text-center text-xs text-ink-muted">
            Each agent reply appears here as a bar split by pipeline stage.
          </p>
        )}
        {metrics.map((m) => (
          <TurnBar key={m.turnId} metric={m} scaleMs={scaleMs} />
        ))}
      </div>
    </section>
  );
}
