"use client";

import { SEGMENT_META } from "@/components/xray/segments";
import { rankedCauses, type StatsResponse } from "@/lib/statsView";

/** Single-hue bar list: the value sits at each bar's tip; the stage name leads the row. */
export function SlowCauses({ causes }: { causes: StatsResponse["slow_turn_causes"] }) {
  const ranked = rankedCauses(causes);
  if (ranked.length === 0) {
    return <p className="text-sm text-ink-muted">No replies over 2 s. Nothing to explain.</p>;
  }
  const max = ranked[0].count;
  return (
    <ul className="space-y-2">
      {ranked.map((c) => (
        <li key={c.key} className="grid grid-cols-[9rem_1fr] items-center gap-3 text-sm">
          <span className="truncate text-ink-muted">{SEGMENT_META[c.key].label}</span>
          <span className="flex items-center gap-2">
            <span
              className="h-4 max-w-full rounded-r-[4px]"
              style={{ width: `${(c.count / max) * 85}%`, backgroundColor: "var(--series-1)" }}
              aria-hidden
            />
            <span className="tabular-nums">
              {c.count} {c.count === 1 ? "reply" : "replies"}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}
