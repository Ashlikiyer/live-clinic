/**
 * Fixed lines the server speaks without the LLM (backend/app/agent/prompt.py), split the way
 * the server's sentence splitter sends them. Kokoro pre-generates them while the landing page
 * is open, so the greeting plays instantly. A unit test keeps them in sync with the backend.
 */

import { speechChunks } from "./turnTaking";

export const GREETING_SENTENCES = [
  "Hi, thanks for calling Bayview Family Clinic.",
  "This is Mia.",
  "Just so you know, this is a demo clinic, so please use made-up details.",
  "How can I help you today?",
];

export const RECOVERY_SENTENCES = [
  "Sorry, I didn't catch that.",
  "Could you say it again?",
  "Sorry, I had a little trouble there.",
  "Could you repeat that?",
  "Sorry, we got cut off.",
  "Where were we?",
];

/**
 * Short openers the prompt asks Mia to start replies with. With these cached, the first audio
 * of most replies plays instantly while the next sentence synthesizes.
 */
export const OPENERS = [
  "Sure.",
  "Of course.",
  "Okay.",
  "Got it.",
  "Great.",
  "Certainly.",
  "Alright.",
  "Absolutely.",
  "No problem.",
  "Thank you.",
  "Thanks.",
  "I see.",
  "Hello!",
  "Hi there!",
];

/** Lookup key for cached clips: "Sure!" and "sure." sound alike, so they share one clip. */
export function phraseKey(text: string): string {
  return text.trim().toLowerCase().replace(/[.!?,]+$/, "");
}

/**
 * The exact pieces the player will ask the voice for (first sentences are split at a comma),
 * in priority order: the greeting is needed first, then openers, then rarer recovery lines.
 */
export function precachePieces(): string[] {
  const first = (s: string) => speechChunks(s, true);
  return [
    ...first(GREETING_SENTENCES[0]),
    ...GREETING_SENTENCES.slice(1),
    ...OPENERS,
    ...first(RECOVERY_SENTENCES[0]),
    RECOVERY_SENTENCES[1],
    ...first(RECOVERY_SENTENCES[2]),
    RECOVERY_SENTENCES[3],
    ...first(RECOVERY_SENTENCES[4]),
    RECOVERY_SENTENCES[5],
  ];
}
