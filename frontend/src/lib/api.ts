/** HTTP helpers: backend URLs, wake-up ping, and the visitor's sandbox session. */

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

const SESSION_KEY = "lcd.session";
/** Don't reuse a session that expires within this window. */
const SESSION_MARGIN_MS = 10 * 60 * 1000;

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

interface StoredSession {
  token: string;
  expiresAt: number;
}

function readStored(): StoredSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredSession;
    return parsed.expiresAt - SESSION_MARGIN_MS > Date.now() ? parsed : null;
  } catch {
    return null;
  }
}

export function forgetSession(): void {
  try {
    window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // Storage unavailable (private mode): nothing to forget.
  }
}

/** The visitor's sandbox token: reused for 24 hours so their bookings persist across calls. */
export async function getSessionToken(): Promise<string> {
  const stored = readStored();
  if (stored) return stored.token;

  const response = await fetch(`${API_URL}/api/sessions`, { method: "POST", credentials: "include" });
  const body = (await response.json().catch(() => null)) as
    | { session_token: string; expires_at: string }
    | { error: { code: string; message: string } }
    | null;
  if (!response.ok || !body || "error" in body) {
    const error = body && "error" in body ? body.error : null;
    throw new ApiError(error?.code ?? "UNAVAILABLE", error?.message ?? "The clinic is unavailable.");
  }
  try {
    window.localStorage.setItem(
      SESSION_KEY,
      JSON.stringify({ token: body.session_token, expiresAt: Date.parse(body.expires_at) }),
    );
  } catch {
    // Storage unavailable: the token still works for this page.
  }
  return body.session_token;
}

export function callSocketUrl(token: string): string {
  return `${WS_URL}/ws/call?token=${encodeURIComponent(token)}`;
}

// ---------- clinic and calendar (session-scoped) ----------

export interface ClinicResponse {
  name: string;
  timezone: string;
  today: string;
  doctors: { id: string; name: string; specialty: string; color: string }[];
}

export interface CalendarResponse {
  date: string;
  busy: { id: string; doctor_id: string; start: string; end: string }[];
  appointments: {
    id: string;
    doctor_id: string;
    start: string;
    end: string;
    state: "holding" | "confirmed" | "cancelled";
    patient_name: string | null;
    expires_at: string | null;
  }[];
}

async function getJson<T>(path: string, token: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: { code: string; message: string } } | null;
    throw new ApiError(body?.error?.code ?? "UNAVAILABLE", body?.error?.message ?? "Request failed.");
  }
  return (await response.json()) as T;
}

export function fetchClinic(token: string): Promise<ClinicResponse> {
  return getJson<ClinicResponse>("/api/clinic", token);
}

export function fetchCalendarDay(token: string, date: string): Promise<CalendarResponse> {
  return getJson<CalendarResponse>(`/api/calendar?date=${encodeURIComponent(date)}`, token);
}
