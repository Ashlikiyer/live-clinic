/**
 * Mia's line is "busy" when Groq's free tier is at its limit (backend/app/call/busy.py).
 * The server then refuses new calls with BUSY_NOTICE, or ends a call with its busy summary.
 * A test keeps both texts in sync with the backend.
 */

export const BUSY_NOTICE = "Mia's line is busy right now. Please try again in a minute.";

/** Did this call end because the line was busy? (Refused at the start, or cut off mid-call.) */
export function isBusyEnding(outcome: string, summary: string): boolean {
  return outcome === "abandoned" && /line is busy|free-tier limit/i.test(summary);
}
