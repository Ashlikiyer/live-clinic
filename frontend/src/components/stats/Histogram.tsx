"use client";

import { useState } from "react";

import { rebin, secondsTick, type Bin } from "@/lib/statsView";

const BIN_MS = 250;
const HEIGHT_PX = 140;
const TARGET_MS = 1500;
const CAP_MS = 6000;

function binLabel(b: Bin): string {
  return b.open ? `${secondsTick(b.startMs)} or more` : `${secondsTick(b.startMs)} to ${secondsTick(b.endMs)}`;
}

/** Single series (one hue, no legend box): replies per 250 ms bin, with the 1.5 s target. */
export function Histogram({ hist }: { hist: Record<string, number> }) {
  const bins = rebin(hist, BIN_MS, CAP_MS);
  const [active, setActive] = useState<number | null>(null);
  if (bins.length === 0) return <p className="text-sm text-ink-muted">No replies yet.</p>;

  const maxCount = Math.max(...bins.map((b) => b.count));
  const yTicks = [0, Math.ceil(maxCount / 2), maxCount].filter((v, i, a) => a.indexOf(v) === i);
  const spanMs = bins.length * BIN_MS;
  const targetPct = Math.min(100, (TARGET_MS / spanMs) * 100);
  const shown = active === null ? null : bins[active];

  return (
    <div>
      <div className="flex gap-2">
        <div className="relative mt-5 w-6 shrink-0 text-right text-[10px] tabular-nums text-ink-muted" style={{ height: HEIGHT_PX }}>
          {yTicks.map((t) => (
            <span key={t} className="absolute right-0 translate-y-1/2" style={{ bottom: (t / maxCount) * HEIGHT_PX }}>
              {t}
            </span>
          ))}
        </div>
        <div className="relative mt-5 flex-1">
          <div className="pointer-events-none absolute inset-0" aria-hidden>
            {yTicks.map((t) => (
              <div key={t} className="absolute inset-x-0 border-t border-line" style={{ bottom: (t / maxCount) * HEIGHT_PX }} />
            ))}
            {targetPct < 100 && (
              <div className="absolute inset-y-0 border-l border-ink-muted/60" style={{ left: `${targetPct}%` }}>
                <span className="absolute -top-5 -translate-x-1/2 whitespace-nowrap rounded bg-surface px-1 text-[10px] text-ink-muted">
                  1.5 s target
                </span>
              </div>
            )}
          </div>
          <div className="relative flex items-end gap-[2px]" style={{ height: HEIGHT_PX }} role="list" aria-label="Replies by reply time">
            {bins.map((b, i) => (
              <div
                key={b.startMs}
                role="listitem"
                tabIndex={0}
                aria-label={`${binLabel(b)}: ${b.count} replies`}
                className="flex h-full min-w-0 flex-1 items-end justify-center outline-none"
                onPointerEnter={() => setActive(i)}
                onPointerLeave={() => setActive(null)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
              >
                <div
                  className={`w-full max-w-6 rounded-t-[4px] transition-[filter] ${active === i ? "brightness-110" : ""}`}
                  style={{ height: `${(b.count / maxCount) * 100}%`, backgroundColor: "var(--series-1)" }}
                />
              </div>
            ))}
          </div>
          <div className="mt-1 flex justify-between text-[10px] tabular-nums text-ink-muted" aria-hidden>
            <span>0 s</span>
            <span>{secondsTick(spanMs / 2)}</span>
            <span>{bins.at(-1)?.open ? `${secondsTick(bins.at(-1)!.startMs)}+` : secondsTick(spanMs)}</span>
          </div>
        </div>
      </div>
      <p className="mt-2 h-5 text-sm" aria-live="polite">
        {shown ? (
          <>
            <span className="font-semibold tabular-nums">{shown.count} replies</span>{" "}
            <span className="text-ink-muted">
              took {binLabel(shown)}
            </span>
          </>
        ) : (
          <span className="text-ink-muted">Hover or focus a bar for its count.</span>
        )}
      </p>
    </div>
  );
}
