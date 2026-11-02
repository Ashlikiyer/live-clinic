"use client";

import { useCallStore } from "@/store/callStore";

const BARS = [0.6, 1, 0.75, 0.9, 0.5];

export function MicMeter() {
  const level = useCallStore((s) => s.micLevel);
  const muted = useCallStore((s) => s.muted);
  const active = level > 0 && !muted;

  return (
    <div
      className="flex h-8 w-10 items-end justify-center gap-0.5"
      role="meter"
      aria-label={muted ? "Microphone muted" : "Microphone level"}
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={muted ? 0 : level}
    >
      {muted ? (
        <span className="text-xs text-danger">muted</span>
      ) : (
        BARS.map((scale, i) => (
          <span
            key={i}
            className={`w-1 rounded-full ${active ? "animate-mic bg-brand" : "bg-line"}`}
            style={{
              height: `${Math.max(20, scale * Math.max(level, 0.25) * 100)}%`,
              animationDelay: `${i * 90}ms`,
            }}
          />
        ))
      )}
    </div>
  );
}
