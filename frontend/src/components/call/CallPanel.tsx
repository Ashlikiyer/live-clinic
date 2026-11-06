"use client";

import { useCallStore, type VoiceMode } from "@/store/callStore";

import { MicBars, Orb } from "./Orb";
import { Transcript } from "./Transcript";
import { TypeInput } from "./TypeInput";

export interface CallControls {
  onEnd: () => void;
  onToggleMute: () => void;
  /** Null when typing isn't available (the scripted demo). */
  onSendText: ((text: string) => void) | null;
  /** The caller is typing: it counts as activity for the silence check. */
  onTyping?: () => void;
  /** Leave the call screen (the logo in the header). */
  onHome: () => void;
  /** Start the scripted demo over (demo calls only). */
  onReplay?: () => void;
}

/** Which voice Mia is speaking with (it can change mid-call if one stops working). */
const VOICE_NAME: Record<VoiceMode, string> = {
  orpheus: "natural voice",
  kokoro: "in-browser voice",
  lite: "built-in voice",
};

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <div role="status" className="mx-2 mt-2 rounded-2xl bg-rose-soft px-3.5 py-2.5 text-xs leading-relaxed text-rose-ink">
      {children}
    </div>
  );
}

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
  const transferring = useCallStore(
    (s) => s.status === "transferring" || s.ended?.outcome === "transferred",
  );
  const active = status === "live" || status === "connecting" || status === "transferring";
  const hearing = userSpeaking && !muted;

  const micLabel =
    kind === "demo"
      ? "Demo: just watch"
      : muted
        ? "Muted"
        : mic === "starting"
          ? "Allow your microphone"
          : mic === "denied"
            ? "Microphone blocked"
            : mic === "unavailable"
              ? "No microphone"
              : mic === "off"
                ? "Typing only"
                : hearing
                  ? "Hearing you"
                  : speaking
                    ? "You can cut in"
                    : "Mic on";

  return (
    <section aria-label="Call" className="flex h-full min-h-0 flex-col overflow-hidden rounded-3xl border border-line bg-surface">
      <div className="m-2 flex flex-col items-center gap-3 rounded-[18px] bg-surface-muted px-[18px] pb-4 pt-[22px]">
        <Orb
          size={120}
          mode={speaking ? "speak" : hearing ? "listen" : "idle"}
          label={speaking ? "Mia is speaking" : "Mia is listening"}
        />
        <div className="flex flex-col items-center gap-0.5">
          <span className="text-[22px] font-medium tracking-[-0.03em]">Mia</span>
          <span className="text-[12.5px] text-ink-faint">
            Bayview receptionist{kind === "live" ? ` · ${VOICE_NAME[voiceMode]}` : ""}
          </span>
        </div>
        <div
          className="flex h-[30px] items-center gap-2 rounded-full bg-surface px-3"
          role="meter"
          aria-label={micLabel}
          aria-valuemin={0}
          aria-valuemax={1}
          aria-valuenow={hearing ? 1 : 0}
        >
          <MicBars on={hearing} />
          <span className="text-[11.5px] font-medium text-ink-muted">{micLabel}</span>
        </div>
        <div className="flex w-full gap-2">
          <button
            type="button"
            onClick={controls.onToggleMute}
            disabled={!active || (kind === "live" && mic !== "listening")}
            aria-pressed={muted}
            className="h-[46px] flex-1 rounded-full border border-line-strong bg-surface text-sm font-medium transition-colors hover:bg-bg disabled:opacity-50"
          >
            {muted ? "Unmute" : "Mute"}
          </button>
          <button
            type="button"
            onClick={controls.onEnd}
            disabled={!active}
            className="h-[46px] flex-1 rounded-full bg-ink text-sm font-medium text-white transition-colors hover:bg-danger disabled:opacity-50"
          >
            End call
          </button>
        </div>
      </div>

      {notice && <Notice>{notice}</Notice>}
      {transferring && <Notice>Transferring you to the front desk…</Notice>}
      {connection === "reconnecting" && <Notice>Connection dropped. Reconnecting…</Notice>}
      {kind === "live" && mic === "denied" && (
        <Notice>
          Your microphone is blocked. Click the lock or site-settings icon in the address bar, allow
          the microphone, then call again. You can type below meanwhile.
        </Notice>
      )}
      {kind === "live" && mic === "unavailable" && (
        <Notice>No microphone found. You can type your messages below instead.</Notice>
      )}

      <div className="px-[18px] pb-0.5 pt-2 text-xs font-medium text-ink-faint">Conversation</div>
      <Transcript />

      <div className="border-t border-line p-2.5">
        <TypeInput
          disabled={!active || controls.onSendText === null}
          onSend={controls.onSendText}
          onTyping={controls.onTyping}
        />
      </div>
    </section>
  );
}
