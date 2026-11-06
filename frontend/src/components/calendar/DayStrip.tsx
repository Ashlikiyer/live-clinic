"use client";

import { useMemo } from "react";

import { addDays, dateOf, formatShortDay, weekStart } from "@/lib/time";
import { useCallStore } from "@/store/callStore";

const arrow =
  "grid size-8 flex-none place-items-center rounded-full text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink";

/** Monday–Saturday of the week being discussed. Jumps whenever the agent changes day. */
export function DayStrip({ date, today }: { date: string; today: string }) {
  const selectDate = useCallStore((s) => s.selectDate);
  const appointments = useCallStore((s) => s.appointments);
  const offered = useCallStore((s) => s.offered);
  const monday = weekStart(date);
  const days = Array.from({ length: 6 }, (_, i) => addDays(monday, i));
  // A dot marks days where this call has something: an offer, a hold or a booking.
  const busyDays = useMemo(() => {
    const set = new Set(Object.values(appointments).map((a) => dateOf(a.start)));
    if (offered) set.add(offered.date);
    return set;
  }, [appointments, offered]);

  return (
    <div className="flex items-center gap-1.5 px-[22px] pb-3.5 max-sm:px-3">
      <button type="button" aria-label="Previous week" onClick={() => selectDate(addDays(monday, -7))} className={arrow}>
        ‹
      </button>
      <div className="grid flex-1 grid-cols-6 gap-1.5">
        {days.map((day) => {
          const selected = day === date;
          return (
            <button
              key={day}
              type="button"
              onClick={() => selectDate(day)}
              aria-current={selected ? "date" : undefined}
              aria-label={`${formatShortDay(day)} ${Number(day.slice(8, 10))}${day === today ? ", today" : ""}`}
              className={`relative flex flex-col items-center gap-0.5 rounded-[14px] py-[9px] transition-colors ${
                selected ? "bg-ink text-white" : "bg-surface-muted text-ink hover:bg-[#efefec]"
              }`}
            >
              <span className="text-[11px] opacity-65">{formatShortDay(day)}</span>
              <span className="text-[17px] font-medium tabular-nums">{Number(day.slice(8, 10))}</span>
              {!selected && busyDays.has(day) && (
                <span className="absolute right-[9px] top-[7px] size-1.5 rounded-full bg-rose" aria-hidden />
              )}
              {day === today && (
                <span className={`absolute bottom-1.5 h-0.5 w-3 rounded-full ${selected ? "bg-white/70" : "bg-ink/40"}`} aria-hidden />
              )}
            </button>
          );
        })}
      </div>
      <button type="button" aria-label="Next week" onClick={() => selectDate(addDays(monday, 7))} className={arrow}>
        ›
      </button>
    </div>
  );
}
