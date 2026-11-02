/**
 * Where the calendar gets a day's schedule: GET /api/calendar during a live call, the mock
 * schedule during the scripted demo. Each day loads once per call.
 */

import { fetchCalendarDay, type CalendarResponse } from "@/lib/api";
import { demoKeepFree, mockBusySlots } from "@/mock/busy";
import { useCallStore } from "@/store/callStore";
import type { CalendarDay } from "@/store/reducer";

type DayLoader = (date: string) => Promise<void>;

const loading = new Set<string>();

async function mockLoader(date: string): Promise<void> {
  useCallStore.getState().setBusyDay(date, mockBusySlots(date, demoKeepFree));
}

let loader: DayLoader = mockLoader;

export function toCalendarDay(response: CalendarResponse): CalendarDay {
  return {
    date: response.date,
    busy: response.busy.map((b) => ({ id: b.id, doctorId: b.doctor_id, start: b.start, end: b.end })),
    appointments: response.appointments.map((a) => ({
      id: a.id,
      doctorId: a.doctor_id,
      start: a.start,
      end: a.end,
      state: a.state,
      patientName: a.patient_name ?? undefined,
      expiresAt: a.expires_at ?? undefined,
      updatedAt: 0,
    })),
  };
}

/** Live calls read the caller's real sandbox calendar. Pass null to go back to the mock. */
export function setCalendarSource(token: string | null): void {
  loading.clear();
  loader = token
    ? async (date) => {
        try {
          useCallStore.getState().loadCalendarDay(toCalendarDay(await fetchCalendarDay(token, date)));
        } catch {
          // Leave the day unloaded; it is retried next time the calendar shows it.
        }
      }
    : mockLoader;
}

export function loadDay(date: string): void {
  if (loading.has(date)) return;
  loading.add(date);
  void loader(date).finally(() => loading.delete(date));
}
