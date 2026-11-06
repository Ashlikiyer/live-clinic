/** The status pill in the desk header: what is happening on the call right now. Pure. */

export type DeskTone = "speaking" | "listening" | "working" | "idle";

export interface DeskStatusInput {
  status: "idle" | "connecting" | "live" | "transferring" | "ended";
  agentSpeaking: boolean;
  userSpeaking: boolean;
  working: boolean;
}

export function deskStatus(s: DeskStatusInput): { label: string; tone: DeskTone } {
  if (s.status === "connecting") return { label: "Connecting…", tone: "idle" };
  if (s.status === "ended") return { label: "Call ended", tone: "idle" };
  if (s.status === "transferring") return { label: "Transferring…", tone: "working" };
  if (s.status === "idle") return { label: "Ready", tone: "idle" };
  if (s.agentSpeaking) return { label: "Mia is speaking", tone: "speaking" };
  if (s.userSpeaking) return { label: "You're speaking", tone: "listening" };
  if (s.working) return { label: "Mia is checking", tone: "working" };
  return { label: "Listening", tone: "listening" };
}

/** "02:34": the call timer, zero-padded like a phone. */
export function callClock(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
