/**
 * Sentence audio queue. Sentences are synthesized as soon as they arrive (so synthesis of
 * sentence 2 overlaps playback of sentence 1) and played strictly in order. `stop()` cuts the
 * audio at once and reports exactly what the caller heard.
 */

import { playedText, speechChunks } from "./turnTaking";

/** One playing sentence. */
export interface Playback {
  ended: Promise<void>;
  stop: () => void;
  /** 0..1, how much of the sentence has played. */
  progress: () => number;
}

export interface Clip {
  play: () => Playback;
}

/**
 * A speech engine: Groq Orpheus (through the server), Kokoro in the browser, or the built-in
 * speechSynthesis "lite" voice.
 */
export interface Voice {
  readonly mode: "orpheus" | "kokoro" | "lite";
  /** Speaks a whole reply per request (server speech has a daily request budget). */
  readonly wholeTurns?: boolean;
  prepare: (text: string) => Promise<Clip>;
  /** Drop queued synthesis work (after an interruption). */
  cancelPending?: () => void;
}

export interface StopResult {
  turnId: number;
  playedText: string;
  playedMs: number;
}

interface Item {
  index: number;
  /** Piece number within the sentence (the first sentence may be split in two). */
  part: number;
  last: boolean;
  text: string;
  clip: Promise<Clip | null>;
}

export interface PlayerCallbacks {
  onSpeakingChange?: (speaking: boolean) => void;
  /** First audio of a turn started; `ttsMs` counts from the first sentence's arrival. */
  onFirstAudio?: (turnId: number, ttsMs: number) => void;
  onIdle?: () => void;
}

/** A sentence that couldn't be synthesized is skipped; say why (a cancel is expected). */
function logVoiceFailure(error: unknown): null {
  const message = error instanceof Error ? error.message : String(error);
  if (message !== "cancelled") console.warn(`[voice] couldn't synthesize a sentence: ${message}`);
  return null;
}

export class SentencePlayer {
  private turnId = -1;
  private queue: Item[] = [];
  private next = { index: 0, part: 0 };
  private finished: string[] = [];
  private current: { text: string; playback: Playback } | null = null;
  private firstSentenceAt: number | null = null;
  private firstAudioSent = false;
  private turnStartedAt = 0;
  private pumping = false;
  private speaking = false;
  /** Stopped by an interruption: ignore late sentences for this turn. */
  private halted = false;
  /** The server has sent every sentence for this turn (agent.text.done). */
  private textDone = false;
  /** A line outside any turn's sentences: the tool filler or a silence nudge. */
  private aside: Playback | null = null;

  constructor(
    private voice: Voice,
    private readonly callbacks: PlayerCallbacks = {},
    private readonly now: () => number = () => performance.now(),
  ) {}

  setVoice(voice: Voice): void {
    this.voice = voice;
  }

  get voiceMode(): Voice["mode"] {
    return this.voice.mode;
  }

  get isSpeaking(): boolean {
    return this.speaking;
  }

  get activeTurnId(): number {
    return this.turnId;
  }

  enqueue(turnId: number, index: number, text: string): void {
    if (turnId < this.turnId) return;
    if (turnId > this.turnId) this.resetFor(turnId);
    if (this.halted) return;
    this.firstSentenceAt ??= this.now();
    // Speaking starts with the turn, not the audio, so barge-in works between sentences too.
    this.setSpeaking(true);
    const pieces = this.voice.wholeTurns ? [text] : speechChunks(text, index === 0);
    pieces.forEach((piece, part) => {
      const clip = this.voice.prepare(piece).catch(logVoiceFailure);
      this.queue.push({ index, part, last: part === pieces.length - 1, text: piece, clip });
    });
    this.queue.sort((a, b) => a.index - b.index || a.part - b.part);
    void this.pump();
  }

  /**
   * Say a short line that isn't part of a reply (e.g. "Let me check that." while a tool runs).
   * Skipped if anything is already playing; the reply's own sentences wait until it ends.
   * Resolves true if the line played to the end.
   */
  async sayAside(text: string): Promise<boolean> {
    if (this.current || this.aside) return false;
    const clip = await this.voice.prepare(text).catch(logVoiceFailure);
    if (!clip || this.current || this.aside) return false;
    const playback = clip.play();
    this.aside = playback;
    this.setSpeaking(true);
    await playback.ended;
    if (this.aside !== playback) return false; // stopped by a barge-in
    this.aside = null;
    if (this.isNextReady()) void this.pump();
    else if (this.current === null && this.queue.length === 0 && !this.pumping) {
      this.setSpeaking(false);
    }
    return true;
  }

  /** All sentences for `turnId` have arrived; speaking ends once they finish playing. */
  markDone(turnId: number): void {
    if (turnId !== this.turnId) return;
    this.textDone = true;
    this.finishIfDrained();
  }

  /** Stop immediately (barge-in). Returns what was heard of the current turn, if anything. */
  stop(): StopResult | null {
    this.aside?.stop();
    this.aside = null;
    return this.stopTurn();
  }

  /** Stop the current turn's sentences; a filler line in progress is left to finish. */
  private stopTurn(): StopResult | null {
    const result =
      this.firstAudioSent
        ? {
            turnId: this.turnId,
            playedText: playedText(
              this.finished,
              this.current?.text ?? null,
              this.current?.playback.progress() ?? 0,
            ),
            playedMs: Math.round(this.now() - this.turnStartedAt),
          }
        : null;
    this.current?.playback.stop();
    this.current = null;
    this.queue = [];
    this.halted = true;
    this.voice.cancelPending?.();
    if (!this.aside) this.setSpeaking(false);
    return result;
  }

  /** Forget everything, e.g. when a new caller turn starts. */
  resetFor(turnId: number): void {
    this.stopTurn();
    this.turnId = turnId;
    this.next = { index: 0, part: 0 };
    this.finished = [];
    this.firstSentenceAt = null;
    this.firstAudioSent = false;
    this.halted = false;
    this.textDone = false;
  }

  private isNextReady(): boolean {
    const head = this.queue[0];
    return head !== undefined && head.index === this.next.index && head.part === this.next.part;
  }

  private finishIfDrained(): void {
    if (this.textDone && this.queue.length === 0 && this.current === null && !this.pumping) {
      this.setSpeaking(false);
      this.callbacks.onIdle?.();
    }
  }

  private setSpeaking(speaking: boolean): void {
    if (this.speaking === speaking) return;
    this.speaking = speaking;
    this.callbacks.onSpeakingChange?.(speaking);
  }

  private async pump(): Promise<void> {
    if (this.pumping) return;
    this.pumping = true;
    try {
      while (this.isNextReady()) {
        const item = this.queue.shift()!;
        const turnId = this.turnId;
        const clip = await item.clip;
        // Interrupted, or a newer turn started while this sentence was synthesizing.
        if (turnId !== this.turnId || this.halted) break;
        this.next = item.last ? { index: item.index + 1, part: 0 } : { index: item.index, part: item.part + 1 };
        if (!clip) continue; // synthesis failed: skip the sentence rather than stall
        // Let a filler line finish rather than talk over it.
        while (this.aside) await this.aside.ended;
        if (turnId !== this.turnId || this.halted) break;

        const playback = clip.play();
        this.current = { text: item.text, playback };
        if (!this.firstAudioSent) {
          this.firstAudioSent = true;
          this.turnStartedAt = this.now();
          const ttsMs = Math.round(this.now() - (this.firstSentenceAt ?? this.now()));
          this.callbacks.onFirstAudio?.(turnId, ttsMs);
        }
        await playback.ended;
        if (turnId !== this.turnId || this.current?.playback !== playback) break;
        this.finished.push(item.text);
        this.current = null;
      }
    } finally {
      this.pumping = false;
    }
    // A newer turn may have queued sentences while this loop was finishing.
    if (this.isNextReady()) void this.pump();
    else this.finishIfDrained();
  }
}
