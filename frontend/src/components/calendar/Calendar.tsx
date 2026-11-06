"use client";

import { useEffect } from "react";

import { formatLongDate } from "@/lib/time";
import { loadDay } from "@/realtime/calendarSource";
import { useCallStore } from "@/store/callStore";

import { DayStrip } from "./DayStrip";
import { DoctorColumns } from "./DoctorColumns";

const LEGEND = [
  { label: "Open", className: "border border-[#d9d9d5] bg-surface" },
  { label: "Taken", className: "bg-line" },
  { label: "Offered", className: "border border-dashed border-ink" },
  { label: "Holding", className: "bg-[oklch(0.9_0.12_92)]" },
  { label: "Booked", className: "bg-[oklch(0.82_0.11_155)]" },
];

export function Calendar() {
  const date = useCallStore((s) => s.calendarDate);
  const today = useCallStore((s) => s.today);
  const hasDay = useCallStore((s) => (date ? date in s.busy : false));

  // The live call's real calendar (GET /api/calendar), or the mock schedule in the demo.
  useEffect(() => {
    if (date && !hasDay) loadDay(date);
  }, [date, hasDay]);

  return (
    <section aria-label="Appointments" className="flex h-full min-h-0 flex-col overflow-hidden rounded-3xl border border-line bg-surface">
      <div className="flex flex-wrap items-end justify-between gap-4 px-[22px] pb-3.5 pt-5">
        <div className="flex flex-col gap-1">
          <span className="text-xs text-ink-faint">Appointments</span>
          <h2 className="text-[26px] font-medium leading-none tracking-[-0.035em]" aria-live="polite">
            {date ? formatLongDate(date) : "Waiting for Mia"}
          </h2>
        </div>
        <ul className="flex flex-wrap gap-3.5 text-[11.5px] text-ink-muted">
          {LEGEND.map((item) => (
            <li key={item.label} className="flex items-center gap-1.5">
              <span className={`size-2.5 rounded-[3px] ${item.className}`} />
              {item.label}
            </li>
          ))}
        </ul>
      </div>
      {date && today ? (
        <>
          <DayStrip date={date} today={today} />
          <DoctorColumns date={date} />
        </>
      ) : (
        <div className="flex flex-1 items-center justify-center text-[13px] text-ink-ghost">
          The schedule appears when Mia picks up.
        </div>
      )}
    </section>
  );
}
