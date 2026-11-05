/** Pure turn-taking rules shared by the VAD wrapper and the call controller. */

export const END_SILENCE_MS = Number(process.env.NEXT_PUBLIC_END_SILENCE_MS ?? 600);
export const BARGE_IN_MIN_MS = Number(process.env.NEXT_PUBLIC_BARGE_IN_MIN_MS ?? 400);

export interface Utterance {
  /** Was the agent talking when the caller started speaking? */
  agentSpeakingAtStart: boolean;
  /** Did that speech last long enough to interrupt the agent? */
  bargedIn: boolean;
}

/**
 * Whether a finished utterance should be sent as a caller turn. While the agent is talking,
 * short sounds ("mm-hmm", a cough) that never reached the barge-in threshold are ignored.
 */
export function shouldSendUtterance(u: Utterance): boolean {
  return !u.agentSpeakingAtStart || u.bargedIn;
}

/** The first `fraction` of the words in `text` (what was heard of a cut-off sentence). */
export function partialWords(text: string, fraction: number): string {
  const words = text.split(/\s+/).filter(Boolean);
  const count = Math.floor(words.length * Math.max(0, Math.min(1, fraction)));
  return words.slice(0, count).join(" ");
}

/** Text the caller actually heard: finished sentences plus part of the one playing. */
export function playedText(finished: string[], current: string | null, fraction: number): string {
  const partial = current ? partialWords(current, fraction) : "";
  return [...finished, partial].filter(Boolean).join(" ");
}

/** The spec's fallback rule: switch to the lite voice after two slow first-audio starts. */
export class SlowVoiceDetector {
  private slowInARow = 0;

  constructor(
    private readonly thresholdMs = 1500,
    private readonly strikes = 2,
  ) {}

  /** Record a first-audio delay; returns true when it's time to fall back. */
  record(ttsMs: number): boolean {
    this.slowInARow = ttsMs > this.thresholdMs ? this.slowInARow + 1 : 0;
    return this.slowInARow >= this.strikes;
  }
}

/**
 * Move a call that started on the lite voice (Kokoro was still loading) over to Kokoro? Only
 * once Kokoro is ready, only between replies, and never after the device proved too slow.
 */
export function shouldSwitchToKokoro(state: {
  kokoroReady: boolean;
  downgraded: boolean;
  mode: "orpheus" | "kokoro" | "lite";
  speaking: boolean;
}): boolean {
  return state.kokoroReady && !state.downgraded && state.mode === "lite" && !state.speaking;
}

const MAX_LEAD_CHARS = 40;
const MIN_REST_CHARS = 12;

/**
 * Speech pieces for one sentence. The first sentence of a reply is split at its first comma
 * ("Sure," + "I can help with that."), so the short lead-in plays while the rest synthesizes.
 */
export function speechChunks(sentence: string, isFirst: boolean): string[] {
  if (!isFirst) return [sentence];
  const comma = sentence.indexOf(", ");
  if (comma < 1 || comma > MAX_LEAD_CHARS) return [sentence];
  const rest = sentence.slice(comma + 2).trim();
  if (rest.length < MIN_REST_CHARS) return [sentence];
  return [sentence.slice(0, comma + 1), rest];
}
