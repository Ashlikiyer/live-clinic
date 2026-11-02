"use client";

import { useEffect, useState } from "react";

import { formatDuration } from "@/lib/time";
import { useCallStore } from "@/store/callStore";

import { MicMeter } from "./MicMeter";
import { Orb } from "./Orb";
import { Transcript } from "./Transcript";
import { TypeInput } from "./TypeInput";

const STATUS_LABEL = {
  idle: "Ready",
  connecting: "Connecting...",
  live: "On call",
  transferring: "Transferring...",
  ended: "Call ended",
} as const;

function useCallTimer(): string {
  const startedAt = useCallStore((s) => s.startedAt);
  const endedAt = useCallStore((s) => s.endedAt);
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    if (endedAt !== null) return;
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [endedAt]);

  if (startedAt === null) return "0:00";
  return formatDuration(((endedAt ?? now ?? startedAt) - startedAt) / 1000);
}

export function CallPanel({ onEnd }: { onEnd: () => void }) {
  const status = useCallStore((s) => s.status);
  const speaking = useCallStore((s) => s.agentSpeaking);
  const muted = useCallStore((s) => s.muted);
  const toggleMute = useCallStore((s) => s.toggleMute);
  const activeTools = useCallStore((s) => s.activeTools);
  const timer = useCallTimer();
  const active = status === "live" || status === "connecting" || status === "transferring";

  return (
    <section
      aria-label="Call"
      className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-line bg-surface"
    >
      <div className="flex items-center gap-4 border-b border-line p-4">
        <Orb speaking={speaking} />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">Mia · Receptionist</p>
          <p className="flex items-center gap-2 text-sm text-ink-muted">
            <span className={`size-2 rounded-full ${active ? "bg-green-500" : "bg-ink-muted"}`} />
            {STATUS_LABEL[status]} · <span className="tabular-nums">{timer}</span>
          </p>
          <p className="h-4 truncate text-xs text-brand" aria-live="polite">
            {activeTools.length > 0 ? `Working: ${activeTools[0].replaceAll("_", " ")}...` : ""}
          </p>
        </div>
        <MicMeter />
      </div>

      <Transcript />

      <div className="space-y-3 border-t border-line p-3">
        <TypeInput disabled={!active} />
        <div className="flex gap-2">
          <button
            type="button"
            onClick={toggleMute}
            disabled={!active}
            aria-pressed={muted}
            className="flex-1 rounded-full border border-line px-4 py-2 text-sm font-medium transition hover:bg-surface-muted disabled:opacity-50"
          >
            {muted ? "Unmute" : "Mute"}
          </button>
          <button
            type="button"
            onClick={onEnd}
            disabled={!active}
            className="flex-1 rounded-full bg-danger px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
          >
            End call
          </button>
        </div>
      </div>
    </section>
  );
}
