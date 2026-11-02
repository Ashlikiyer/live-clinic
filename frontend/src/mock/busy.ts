/** Phase 0 stand-in for GET /api/calendar: deterministic fake busy slots per day. */

import {
  CLOSE_MINUTES,
  DOCTORS,
  LUNCH_END_MINUTES,
  LUNCH_START_MINUTES,
  OPEN_MINUTES,
  SLOT_MINUTES,
} from "@/lib/clinic";
import { atMinutes, weekday } from "@/lib/time";
import { slotKey, type BusySlot } from "@/store/reducer";

/** FNV-1a: a tiny stable hash so the same day always looks the same. */
function hash(text: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0) / 0xffffffff;
}

export function mockBusySlots(date: string, keepFree: ReadonlySet<string> = new Set()): BusySlot[] {
  if (weekday(date) === 0) return [];
  const slots: BusySlot[] = [];
  for (const doctor of DOCTORS) {
    for (let m = OPEN_MINUTES; m < CLOSE_MINUTES; m += SLOT_MINUTES) {
      if (m >= LUNCH_START_MINUTES && m < LUNCH_END_MINUTES) continue;
      const start = atMinutes(date, m);
      if (keepFree.has(slotKey(doctor.id, start))) continue;
      if (hash(`${date}|${doctor.id}|${m}`) < 0.5) {
        slots.push({
          id: `seed-${doctor.id}-${start}`,
          doctorId: doctor.id,
          start,
          end: atMinutes(date, m + SLOT_MINUTES),
        });
      }
    }
  }
  return slots;
}

/** Slots the running demo script will book; the mock schedule keeps them free. */
export const demoKeepFree = new Set<string>();
