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

const initials = (name: string) =>
  name
    .replace(/^Dr\.\s*/, "")
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2);

const COLUMNS = "grid-cols-[52px_repeat(3,minmax(5.5rem,1fr))]";

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
    <div className="min-h-0 flex-1 overflow-auto border-t border-line">
      <div className={`sticky top-0 z-20 grid ${COLUMNS} gap-1.5 border-b border-line bg-surface px-[22px] py-3 max-sm:px-3`}>
        <span />
        {doctors.map((d) => (
          <div key={d.id} className="flex min-w-0 items-center gap-2.5">
            <span className="grid size-[30px] flex-none place-items-center rounded-full border border-line bg-surface-muted text-[11px] font-semibold max-xl:hidden">
              {initials(d.name)}
            </span>
            <div className="flex min-w-0 flex-col">
              <span className="truncate text-[13px] font-semibold">{d.name}</span>
              <span className="truncate text-[11.5px] text-ink-faint">{d.specialty}</span>
            </div>
          </div>
        ))}
      </div>

      {closed ? (
        <p className="p-8 text-center text-[13px] text-ink-ghost">Closed on Sundays.</p>
      ) : (
        <div
          className={`relative grid ${COLUMNS} gap-x-1.5 gap-y-[5px] px-[22px] pb-[18px] pt-3 max-sm:px-3`}
          style={{ gridTemplateRows: `repeat(${SLOTS_PER_DAY}, 38px)` }}
        >
          {ROW_STARTS.map((m, row) => (
            <span
              key={`label-${m}`}
              className="self-center font-mono text-[11px] text-ink-ghost"
              style={{ gridRow: row + 1, gridColumn: 1 }}
            >
              {formatTime(atMinutes(date, m)).replace(/\s?[AP]M$/, "")}
            </span>
          ))}

          <div
            className="bg-stripes flex items-center justify-center rounded-[10px] text-[11px] text-ink-ghost"
            style={{
              gridColumn: "2 / -1",
              gridRow: `${(LUNCH_START_MINUTES - OPEN_MINUTES) / SLOT_MINUTES + 1} / span ${(LUNCH_END_MINUTES - LUNCH_START_MINUTES) / SLOT_MINUTES}`,
            }}
          >
            Lunch break · 12:00–1:00
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
