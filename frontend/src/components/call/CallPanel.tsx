"use client";

import { useEffect, useState } from "react";

import { formatDuration } from "@/lib/time";
import { useCallStore, type VoiceMode } from "@/store/callStore";

import { MicMeter } from "./MicMeter";
import { Orb } from "./Orb";
import { Transcript } from "./Transcript";
import { TypeInput } from "./TypeInput";

export interface CallControls {
  onEnd: () => void;
  onToggleMute: () => void;
  /** Null when typing isn't available (the scripted demo). */
  onSendText: ((text: string) => void) | null;
  /** The caller is typing: it counts as activity for the silence check. */
  onTyping?: () => void;
}

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

function Banner({ tone, children }: { tone: "info" | "warn"; children: React.ReactNode }) {
  return (
    <div
      role="status"
      className={`mx-3 mt-3 rounded-xl px-3 py-2 text-xs leading-relaxed ${
        tone === "warn"
          ? "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-100"
          : "bg-surface-muted text-ink-muted"
      }`}
    >
      {children}
    </div>
  );
}


/** Which voice Mia is speaking with (it can change mid-call if one stops working). */
const VOICE_BADGE: Record<VoiceMode, { label: string; title: string }> = {
  orpheus: { label: "natural voice", title: "Groq Orpheus, generated on the server" },
  kokoro: { label: "in-browser voice", title: "Kokoro, generated on this device" },
  lite: { label: "built-in voice", title: "Using your browser's built-in voice" },
};

export function CallPanel({ controls }: { controls: CallControls }) {
  const status = useCallStore((s) => s.status);
  const kind = useCallStore((s) => s.kind);
  const speaking = useCallStore((s) => s.agentSpeaking);
  const userSpeaking = useCallStore((s) => s.userSpeaking);
  const muted = useCallStore((s) => s.muted);
  const mic = useCallStore((s) => s.mic);
  const voiceMode = useCallStore((s) => s.voiceMode);
  const connection = useCallStore((s) => s.connection);
  const notice = useCallStore((s) => s.notice);
  const activeTools = useCallStore((s) => s.activeTools);
  const transferring = useCallStore(
    (s) => s.status === "transferring" || s.ended?.outcome === "transferred",
  );
  const timer = useCallTimer();
  const active = status === "live" || status === "connecting" || status === "transferring";

  const activity = activeTools.length
    ? `Working: ${activeTools[0].replaceAll("_", " ")}...`
    : userSpeaking
      ? "Listening..."
      : "";

  return (
    <section
      aria-label="Call"
      className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-line bg-surface"
    >
      <div className="flex items-center gap-4 border-b border-line p-4">
        <Orb speaking={speaking} />
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 font-semibold">
            Mia · Receptionist
            {kind === "live" && (
              <span
                className="rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-medium text-ink-muted"
                title={VOICE_BADGE[voiceMode].title}
              >
                {VOICE_BADGE[voiceMode].label}
              </span>
            )}
          </p>
          <p className="flex items-center gap-2 text-sm text-ink-muted">
            <span className={`size-2 rounded-full ${active ? "bg-green-500" : "bg-ink-muted"}`} />
            {STATUS_LABEL[status]} · <span className="tabular-nums">{timer}</span>
          </p>
          <p className="h-4 truncate text-xs text-brand" aria-live="polite">
            {activity}
          </p>
        </div>
        <MicMeter />
      </div>

      {notice && <Banner tone="warn">{notice}</Banner>}
      {transferring && <Banner tone="info">Transferring to front desk staff...</Banner>}
      {connection === "reconnecting" && (
        <Banner tone="warn">Connection dropped. Reconnecting...</Banner>
      )}
      {kind === "live" && mic === "denied" && (
        <Banner tone="warn">
          Microphone blocked. To talk to Mia, click the lock or site-settings icon in the address
          bar, allow the microphone, then call again. You can type below meanwhile.
        </Banner>
      )}
      {kind === "live" && mic === "unavailable" && (
        <Banner tone="warn">No microphone found. You can type your messages below instead.</Banner>
      )}
      {kind === "live" && mic === "starting" && (
        <Banner tone="info">Allow microphone access when your browser asks.</Banner>
      )}
      {kind === "demo" && (
        <Banner tone="info">Scripted demo: no microphone needed. Just watch.</Banner>
      )}

      <Transcript />

      <div className="space-y-3 border-t border-line p-3">
        <TypeInput
          disabled={!active || controls.onSendText === null}
          onSend={controls.onSendText}
          onTyping={controls.onTyping}
        />
        <div className="flex gap-2">
          <button
            type="button"
            onClick={controls.onToggleMute}
            disabled={!active || (kind === "live" && mic !== "listening")}
            aria-pressed={muted}
            className="flex-1 rounded-full border border-line px-4 py-2 text-sm font-medium transition hover:bg-surface-muted disabled:opacity-50"
          >
            {muted ? "Unmute" : "Mute"}
          </button>
          <button
            type="button"
            onClick={controls.onEnd}
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
