"use client";

import { useMemo } from "react";

import {
  CLOSE_MINUTES,
  LUNCH_END_MINUTES,
  LUNCH_START_MINUTES,
  OPEN_MINUTES,
  SLOTS_PER_DAY,
  SLOT_MINUTES,
} from "@/lib/clinic";
import { atMinutes, dateOf, formatTime, minutesOf, weekday } from "@/lib/time";
import { useCallStore } from "@/store/callStore";
import { slotKey } from "@/store/reducer";

import { Slot, gridPlacement } from "./Slot";

const ROW_STARTS = Array.from({ length: SLOTS_PER_DAY }, (_, i) => OPEN_MINUTES + i * SLOT_MINUTES);
const isLunch = (m: number) => m >= LUNCH_START_MINUTES && m < LUNCH_END_MINUTES;

export function DoctorColumns({ date }: { date: string }) {
  const busy = useCallStore((s) => s.busy[date]);
  const appointments = useCallStore((s) => s.appointments);
  const offered = useCallStore((s) => s.offered);
  const doctors = useCallStore((s) => s.doctors);
  const dayAppointments = useMemo(
    () => Object.values(appointments).filter((a) => dateOf(a.start) === date),
    [appointments, date],
  );
  const offeredKeys = new Set(offered?.date === date ? offered.keys : []);
  const closed = weekday(date) === 0;

  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <div className="sticky top-0 z-20 grid grid-cols-[3.5rem_repeat(3,minmax(5.5rem,1fr))] gap-1 border-b border-line bg-surface px-2 py-2">
        <span />
        {doctors.map((d) => (
          <div key={d.id} className="min-w-0 text-center">
            <p className="truncate text-xs font-semibold" style={{ color: d.color }}>
              {d.name}
            </p>
            <p className="truncate text-[11px] text-ink-muted">{d.specialty}</p>
          </div>
        ))}
      </div>

      {closed ? (
        <p className="p-8 text-center text-sm text-ink-muted">Closed on Sundays.</p>
      ) : (
        <div
          className="relative grid grid-cols-[3.5rem_repeat(3,minmax(5.5rem,1fr))] gap-1 p-2"
          style={{ gridTemplateRows: `repeat(${SLOTS_PER_DAY}, minmax(2.25rem, 1fr))` }}
        >
          {ROW_STARTS.map((m, row) => (
            <span
              key={`label-${m}`}
              className="pr-1 text-right text-[11px] tabular-nums text-ink-muted"
              style={{ gridRow: row + 1, gridColumn: 1 }}
            >
              {formatTime(atMinutes(date, m))}
            </span>
          ))}

          <div
            className="flex items-center justify-center rounded-lg bg-surface-muted text-xs text-ink-muted"
            style={{
              gridColumn: "2 / -1",
              gridRow: `${(LUNCH_START_MINUTES - OPEN_MINUTES) / SLOT_MINUTES + 1} / span ${(LUNCH_END_MINUTES - LUNCH_START_MINUTES) / SLOT_MINUTES}`,
            }}
          >
            Lunch break
          </div>

          {doctors.map((doctor, col) =>
            ROW_STARTS.filter((m) => !isLunch(m) && m < CLOSE_MINUTES).map((m) => {
              const start = atMinutes(date, m);
              return (
                <Slot
                  key={`free-${doctor.id}-${m}`}
                  kind="free"
                  offered={offeredKeys.has(slotKey(doctor.id, start))}
                  offeredAt={offered?.at}
                  style={gridPlacement(col, minutesOf(start), SLOT_MINUTES)}
                />
              );
            }),
          )}

          {(busy ?? []).map((slot) => {
            const col = doctors.findIndex((d) => d.id === slot.doctorId);
            if (col === -1) return null;
            return (
              <Slot
                key={slot.id}
                kind="busy"
                style={gridPlacement(col, minutesOf(slot.start), minutesOf(slot.end) - minutesOf(slot.start))}
              />
            );
          })}

          {dayAppointments.map((a) => {
            const col = doctors.findIndex((d) => d.id === a.doctorId);
            if (col === -1) return null;
            return (
              <Slot
                key={a.id}
                kind={a.state}
                layoutId={a.id}
                label={a.patientName}
                time={formatTime(a.start)}
                style={gridPlacement(col, minutesOf(a.start), minutesOf(a.end) - minutesOf(a.start))}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
