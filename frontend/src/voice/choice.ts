/** Which voice a call starts with, from the caller's choice on the landing page. Pure. */

export type VoiceChoice = "orpheus" | "kokoro" | "lite";

export const VOICE_CHOICES: { value: VoiceChoice; label: string; hint: string }[] = [
  { value: "orpheus", label: "Natural", hint: "Groq Orpheus, from the server. Works on any device." },
  { value: "kokoro", label: "In-browser", hint: "Kokoro, runs on your device's GPU (~160 MB once)." },
  { value: "lite", label: "Built-in", hint: "Your browser's own voice. No download." },
];

export const DEFAULT_VOICE: VoiceChoice = "orpheus";

/** What the Kokoro loader can report (a subset of KokoroStatus). */
export type KokoroState = "idle" | "loading" | "ready" | "too_slow" | "failed";

export type VoicePlan =
  | { kind: "orpheus" }
  | { kind: "kokoro" }
  /** `waitForKokoro`: Kokoro is still loading; start on the built-in voice, switch when ready. */
  | { kind: "lite"; waitForKokoro: boolean };

export function planVoice(choice: VoiceChoice, kokoro: KokoroState, liteAvailable: boolean): VoicePlan {
  if (choice === "orpheus") return { kind: "orpheus" };
  if (choice === "kokoro") {
    if (kokoro === "ready" || !liteAvailable) return { kind: "kokoro" };
    return { kind: "lite", waitForKokoro: kokoro === "loading" || kokoro === "idle" };
  }
  // A browser without speechSynthesis can't use the built-in voice: server speech instead.
  return liteAvailable ? { kind: "lite", waitForKokoro: false } : { kind: "orpheus" };
}

/** The saved choice, if it's a valid one. */
export function parseVoiceChoice(saved: string | null | undefined): VoiceChoice {
  return VOICE_CHOICES.some((c) => c.value === saved) ? (saved as VoiceChoice) : DEFAULT_VOICE;
}
