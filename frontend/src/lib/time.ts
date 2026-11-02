/**
 * Clinic-time helpers. Asia/Manila is UTC+8 all year (no daylight saving), so clinic-local
 * ISO strings can carry a fixed "+08:00" offset. Dates are "YYYY-MM-DD" strings.
 */

export const CLINIC_TIMEZONE = "Asia/Manila";
export const CLINIC_OFFSET = "+08:00";

const dateFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: CLINIC_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const timeFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: CLINIC_TIMEZONE,
  hour: "numeric",
  minute: "2-digit",
});

const longDateFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  weekday: "long",
  month: "long",
  day: "numeric",
});

const shortDayFormatter = new Intl.DateTimeFormat("en-US", { timeZone: "UTC", weekday: "short" });

/** Today's date in the clinic's timezone. */
export function clinicDate(now: Date): string {
  return dateFormatter.format(now);
}

function utcNoon(date: string): Date {
  return new Date(`${date}T12:00:00Z`);
}

export function addDays(date: string, days: number): string {
  const d = utcNoon(date);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** 0 = Sunday ... 6 = Saturday. */
export function weekday(date: string): number {
  return utcNoon(date).getUTCDay();
}

/** Monday of the week containing `date` (Sunday belongs to the week before). */
export function weekStart(date: string): string {
  return addDays(date, -((weekday(date) + 6) % 7));
}

/** Clinic-local ISO timestamp, e.g. at("2026-11-04", "14:30") -> "2026-11-04T14:30:00+08:00". */
export function at(date: string, hhmm: string): string {
  return `${date}T${hhmm}:00${CLINIC_OFFSET}`;
}

export function dateOf(iso: string): string {
  return iso.slice(0, 10);
}

/** Minutes since midnight in clinic time, read straight from a clinic-local ISO string. */
export function minutesOf(iso: string): number {
  return Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16));
}

export function formatTime(iso: string): string {
  return timeFormatter.format(new Date(iso));
}

export function formatLongDate(date: string): string {
  return longDateFormatter.format(utcNoon(date));
}

export function formatShortDay(date: string): string {
  return shortDayFormatter.format(utcNoon(date));
}

export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

/** Clinic-local ISO timestamp `minutes` after midnight on `date`. */
export function atMinutes(date: string, minutes: number): string {
  const hh = String(Math.floor(minutes / 60)).padStart(2, "0");
  const mm = String(minutes % 60).padStart(2, "0");
  return at(date, `${hh}:${mm}`);
}

/** Shift a clinic-local ISO timestamp by whole minutes within the same day. */
export function addMinutes(iso: string, minutes: number): string {
  return atMinutes(dateOf(iso), minutesOf(iso) + minutes);
}
