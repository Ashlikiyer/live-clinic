"use client";

import { useEffect } from "react";

import { formatLongDate } from "@/lib/time";
import { loadDay } from "@/realtime/calendarSource";
import { useCallStore } from "@/store/callStore";

import { DayStrip } from "./DayStrip";
import { DoctorColumns } from "./DoctorColumns";

const LEGEND = [
  { label: "Free", className: "border border-dashed border-line bg-surface" },
  { label: "Busy", className: "bg-busy" },
  { label: "Holding", className: "bg-holding" },
  { label: "Confirmed", className: "bg-confirmed" },
  { label: "Cancelled", className: "bg-cancelled" },
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
    <section
      aria-label="Calendar"
      className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-line bg-surface"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-4 py-3">
        <h2 className="font-semibold">Calendar</h2>
        <p className="text-sm text-ink-muted" aria-live="polite">
          {date ? formatLongDate(date) : "Waiting for the call..."}
        </p>
      </div>
      {date && today ? (
        <>
          <DayStrip date={date} today={today} />
          <DoctorColumns date={date} />
          <ul className="flex flex-wrap gap-x-4 gap-y-1 border-t border-line px-4 py-2 text-xs text-ink-muted">
            {LEGEND.map((item) => (
              <li key={item.label} className="flex items-center gap-1.5">
                <span className={`size-3 rounded ${item.className}`} />
                {item.label}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <div className="flex flex-1 items-center justify-center text-sm text-ink-muted">
          The schedule appears when Mia picks up.
        </div>
      )}
    </section>
  );
}
