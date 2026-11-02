"use client";

import { useState } from "react";

import { Calendar } from "@/components/calendar/Calendar";
import { CallPanel, type CallControls } from "@/components/call/CallPanel";
import { IntakeForm } from "@/components/form/IntakeForm";
import { LatencyStrip } from "@/components/xray/LatencyStrip";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { CLINIC_NAME } from "@/lib/clinic";
import { useCallStore } from "@/store/callStore";

export type { CallControls };

type Tab = "calendar" | "form";

export function CallDesk({ controls }: { controls: CallControls }) {
  const [tab, setTab] = useState<Tab>("calendar");
  const desktop = useMediaQuery("(min-width: 1024px)");
  const unseen = useCallStore((s) => s.unseen);
  const markSeen = useCallStore((s) => s.markSeen);

  const selectTab = (next: Tab) => {
    setTab(next);
    markSeen(next);
  };

  return (
    <div className="flex min-h-dvh flex-col lg:h-dvh">
      <header className="flex items-center justify-between gap-4 border-b border-line bg-surface px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-lg bg-brand-soft font-bold text-brand">
            +
          </span>
          <span className="font-semibold">{CLINIC_NAME}</span>
          <span className="hidden text-sm text-ink-muted sm:inline">· Live Clinic Desk</span>
        </div>
        <span className="shrink-0 whitespace-nowrap rounded-full bg-surface-muted px-3 py-1 text-xs text-ink-muted">
          Demo · fake data only
        </span>
      </header>

      {desktop ? (
        <main className="grid min-h-0 flex-1 grid-cols-[minmax(300px,340px)_1fr_minmax(300px,340px)] gap-3 p-3">
          <CallPanel controls={controls} />
          <Calendar />
          <IntakeForm />
        </main>
      ) : (
      <main className="flex flex-1 flex-col gap-3 p-3">
        <div className="h-[46dvh] min-h-80">
          <CallPanel controls={controls} />
        </div>
        <div role="tablist" aria-label="Clinic panels" className="grid grid-cols-2 rounded-xl bg-surface-muted p-1 text-sm">
          {(["calendar", "form"] as const).map((t) => (
            <button
              key={t}
              role="tab"
              type="button"
              aria-selected={tab === t}
              onClick={() => selectTab(t)}
              className={`relative rounded-lg py-2 font-medium ${tab === t ? "bg-surface shadow-sm" : "text-ink-muted"}`}
            >
              {t === "calendar" ? "Calendar" : "Intake form"}
              {unseen[t] && tab !== t && (
                <span className="absolute right-3 top-2 size-2 rounded-full bg-brand" aria-label="updated" />
              )}
            </button>
          ))}
        </div>
        <div className="min-h-[60dvh]">{tab === "calendar" ? <Calendar /> : <IntakeForm />}</div>
      </main>
      )}

      <LatencyStrip compact={!desktop} />
    </div>
  );
}
