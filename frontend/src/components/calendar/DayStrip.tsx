"use client";

import { addDays, formatShortDay, weekStart } from "@/lib/time";
import { useCallStore } from "@/store/callStore";

/** Monday–Saturday of the week being discussed. Jumps whenever the agent changes day. */
export function DayStrip({ date, today }: { date: string; today: string }) {
  const selectDate = useCallStore((s) => s.selectDate);
  const monday = weekStart(date);
  const days = Array.from({ length: 6 }, (_, i) => addDays(monday, i));

  return (
    <div className="flex items-center gap-1 border-b border-line px-2 py-2">
      <button
        type="button"
        aria-label="Previous week"
        onClick={() => selectDate(addDays(monday, -7))}
        className="rounded-lg px-2 py-1 text-ink-muted hover:bg-surface-muted"
      >
        ‹
      </button>
      <div className="grid flex-1 grid-cols-6 gap-1">
        {days.map((day) => {
          const selected = day === date;
          return (
            <button
              key={day}
              type="button"
              onClick={() => selectDate(day)}
              aria-current={selected ? "date" : undefined}
              className={`rounded-lg py-1.5 text-center transition-colors duration-200 ${
                selected ? "bg-brand text-brand-ink" : "hover:bg-surface-muted"
              }`}
            >
              <span className="block text-[11px] uppercase tracking-wide opacity-80">
                {formatShortDay(day)}
              </span>
              <span className="block text-sm font-semibold tabular-nums">
                {Number(day.slice(8, 10))}
              </span>
              {day === today && (
                <span className={`mx-auto mt-0.5 block size-1 rounded-full ${selected ? "bg-brand-ink" : "bg-brand"}`} />
              )}
            </button>
          );
        })}
      </div>
      <button
        type="button"
        aria-label="Next week"
        onClick={() => selectDate(addDays(monday, 7))}
        className="rounded-lg px-2 py-1 text-ink-muted hover:bg-surface-muted"
      >
        ›
      </button>
    </div>
  );
}
