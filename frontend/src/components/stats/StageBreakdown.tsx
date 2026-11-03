"use client";

import { useState } from "react";

import { SEGMENT_META } from "@/components/xray/segments";
import { stageBreakdown, type StatsResponse } from "@/lib/statsView";
import { formatMs } from "@/lib/time";

/** Below this share a segment is too narrow for its label; the legend and tooltip carry it. */
const LABEL_MIN_SHARE = 0.11;

/** Label ink inside each fill, picked by the fill's luminance (both themes' steps agree). */
const LABEL_INK: Record<string, string> = {
  vad_wait_ms: "#ffffff",
  upload_ms: "#111111",
  stt_ms: "#111111",
  llm_ttft_ms: "#111111",
  first_sentence_ms: "#111111",
  tts_ms: "#ffffff",
};

export function StageBreakdown({ medians }: { medians: StatsResponse["stage_medians"] }) {
  const parts = stageBreakdown(medians);
  const [active, setActive] = useState<string | null>(null);
  const [showTable, setShowTable] = useState(false);
  const shown = parts.find((p) => p.key === active);

  return (
    <div>
      {showTable ? (
        <table className="w-full text-left text-sm">
          <thead className="text-ink-muted">
            <tr>
              <th className="py-1 font-medium">Stage</th>
              <th className="py-1 text-right font-medium">Median</th>
              <th className="py-1 text-right font-medium">Share</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {parts.map((p) => (
              <tr key={p.key} className="border-t border-line">
                <td className="py-1">{SEGMENT_META[p.key].label}</td>
                <td className="py-1 text-right">{p.ms} ms</td>
                <td className="py-1 text-right">{Math.round(p.share * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <>
          <div className="flex h-9 gap-[2px]" role="list" aria-label="Median time per stage">
            {parts.map((p, i) => (
              <div
                key={p.key}
                role="listitem"
                tabIndex={0}
                aria-label={`${SEGMENT_META[p.key].label}: ${p.ms} ms (${Math.round(p.share * 100)}%)`}
                onPointerEnter={() => setActive(p.key)}
                onPointerLeave={() => setActive(null)}
                onFocus={() => setActive(p.key)}
                onBlur={() => setActive(null)}
                className={`flex min-w-[3px] items-center justify-center overflow-visible text-xs font-medium outline-none transition-[filter] ${
                  i === 0 ? "rounded-l-[4px]" : ""
                } ${i === parts.length - 1 ? "rounded-r-[4px]" : ""} ${active === p.key ? "brightness-110" : ""}`}
                style={{ flexGrow: p.share, flexBasis: 0, backgroundColor: SEGMENT_META[p.key].color }}
              >
                {p.share >= LABEL_MIN_SHARE && (
                  <span className="whitespace-nowrap" style={{ color: LABEL_INK[p.key] }}>
                    {formatMs(p.ms)}
                  </span>
                )}
              </div>
            ))}
          </div>
          <p className="mt-2 h-5 text-sm" aria-live="polite">
            {shown ? (
              <>
                <span className="font-semibold tabular-nums">{formatMs(shown.ms)}</span>{" "}
                <span className="text-ink-muted">
                  {SEGMENT_META[shown.key].label} · {Math.round(shown.share * 100)}% of a typical reply
                </span>
              </>
            ) : (
              <span className="text-ink-muted">Hover or focus a segment for its exact time.</span>
            )}
          </p>
        </>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted">
        {parts.map((p) => (
          <span key={p.key} className="flex items-center gap-1.5">
            <span aria-hidden className="size-2.5 rounded-[2px]" style={{ backgroundColor: SEGMENT_META[p.key].color }} />
            {SEGMENT_META[p.key].label}
          </span>
        ))}
        <button
          type="button"
          onClick={() => setShowTable((v) => !v)}
          aria-pressed={showTable}
          className="ml-auto rounded-full border border-line px-3 py-0.5 hover:bg-surface-muted"
        >
          {showTable ? "Chart" : "Table"}
        </button>
      </div>
    </div>
  );
}
