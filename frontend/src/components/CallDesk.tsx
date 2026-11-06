"use client";

import { useState } from "react";

import { Calendar } from "@/components/calendar/Calendar";
import { CallPanel, type CallControls } from "@/components/call/CallPanel";
import { IntakeForm } from "@/components/form/IntakeForm";
import { useCallTimer } from "@/hooks/useCallTimer";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { deskStatus, type DeskTone } from "@/lib/deskStatus";
import { useCallStore } from "@/store/callStore";

export type { CallControls };

type Tab = "calendar" | "form";

const TONE_DOT: Record<DeskTone, string> = {
  speaking: "bg-rose",
  listening: "bg-live",
  working: "bg-thinking",
  idle: "bg-ink-ghost",
};

function StatusPill() {
  const status = useCallStore((s) => s.status);
  const agentSpeaking = useCallStore((s) => s.agentSpeaking);
  const userSpeaking = useCallStore((s) => s.userSpeaking);
  const working = useCallStore((s) => s.activeTools.length > 0);
  const timer = useCallTimer();
  const { label, tone } = deskStatus({ status, agentSpeaking, userSpeaking, working });
  return (
    <div className="flex h-9 items-center gap-2.5 rounded-full border border-line pl-3 pr-4 text-[13px]" aria-live="polite">
      <span className={`size-2 rounded-full ${TONE_DOT[tone]}`} />
      <span className="font-medium">{label}</span>
      <span className="text-[#d0d0cc]" aria-hidden>
        |
      </span>
      <span className="font-mono text-[12.5px] text-ink-muted" aria-label={`Call time ${timer}`}>
        {timer}
      </span>
    </div>
  );
}

export function CallDesk({ controls }: { controls: CallControls }) {
  const [tab, setTab] = useState<Tab>("calendar");
  const desktop = useMediaQuery("(min-width: 1024px)");
  const kind = useCallStore((s) => s.kind);
  const unseen = useCallStore((s) => s.unseen);
  const markSeen = useCallStore((s) => s.markSeen);

  const selectTab = (next: Tab) => {
    setTab(next);
    markSeen(next);
  };

  return (
    <div className="flex min-h-dvh flex-col bg-surface lg:h-dvh lg:min-h-[720px]">
      <header className="flex flex-none flex-wrap items-center justify-between gap-4 border-b border-line px-5 py-3.5 max-sm:px-3">
        <button type="button" onClick={controls.onHome} className="flex items-center gap-2.5" aria-label="Back to the start page">
          <span className="grid size-6 place-items-center rounded-full bg-ink">
            <span className="size-[7px] rounded-full bg-white" />
          </span>
          <span className="text-[17px] font-semibold tracking-[-0.02em]">Bayview</span>
          <span className="text-[13px] text-ink-ghost max-sm:hidden">Front desk</span>
        </button>
        <StatusPill />
        <div className="flex items-center gap-2 max-md:hidden">
          <span className="whitespace-nowrap rounded-full bg-rose-soft px-3 py-1.5 text-xs font-medium text-rose-ink">
            Demo · fake data
          </span>
          {kind === "demo" && controls.onReplay && (
            <button
              type="button"
              onClick={controls.onReplay}
              className="h-9 whitespace-nowrap rounded-full border border-line-strong bg-surface px-4 text-[12.5px] font-medium hover:bg-surface-muted"
            >
              Replay demo
            </button>
          )}
        </div>
      </header>

      {desktop ? (
        <main className="grid min-h-0 flex-1 grid-cols-[minmax(300px,340px)_minmax(0,1fr)_minmax(280px,330px)] gap-3 bg-bg p-3">
          <CallPanel controls={controls} />
          <Calendar />
          <IntakeForm />
        </main>
      ) : (
        <main className="flex flex-1 flex-col gap-3 bg-bg p-3">
          <div className="h-[62dvh] min-h-[440px]">
            <CallPanel controls={controls} />
          </div>
          <div role="tablist" aria-label="Clinic panels" className="grid grid-cols-2 gap-1 rounded-full border border-line bg-surface p-1 text-sm">
            {(["calendar", "form"] as const).map((t) => (
              <button
                key={t}
                role="tab"
                type="button"
                aria-selected={tab === t}
                onClick={() => selectTab(t)}
                className={`relative rounded-full py-2 font-medium transition-colors ${
                  tab === t ? "bg-ink text-white" : "text-ink-muted"
                }`}
              >
                {t === "calendar" ? "Appointments" : "Your details"}
                {unseen[t] && tab !== t && (
                  <span className="absolute right-4 top-2 size-1.5 rounded-full bg-rose" aria-label="updated" />
                )}
              </button>
            ))}
          </div>
          <div className="h-[70dvh] min-h-[480px]">{tab === "calendar" ? <Calendar /> : <IntakeForm />}</div>
        </main>
      )}
    </div>
  );
}
