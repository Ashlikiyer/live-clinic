/**
 * Server speech: Groq Orpheus, asked for through the call socket (`tts.request`) and streamed
 * back as 16-bit PCM chunks (`tts.audio` frames, then `tts.done` or `tts.failed`).
 *
 * Unlike Kokoro it speaks a whole reply per request (`wholeTurns`), because the free tier
 * allows 100 requests a day. Playback starts at the first chunk; later chunks are scheduled
 * back to back, so the reply plays without gaps while the rest is still arriving.
 */

import type { Clip, Playback, Voice } from "./player";
import { getAudioContext } from "./tts";

/** 16-bit little-endian PCM -> Web Audio float samples (-1..1). Pure. */
export function pcm16ToFloat32(pcm: ArrayBuffer): Float32Array {
  const view = new DataView(pcm);
  const out = new Float32Array(Math.floor(pcm.byteLength / 2));
  for (let i = 0; i < out.length; i++) out[i] = view.getInt16(i * 2, true) / 0x8000;
  return out;
}

/** Plays audio that is still arriving. Separate from Web Audio so the voice can be tested. */
export interface StreamClip extends Clip {
  push: (samples: Float32Array) => void;
  finish: () => void;
}

export type ClipFactory = (sampleRate: number) => StreamClip;

/** The browser implementation: each chunk becomes a buffer source scheduled after the last. */
export function webAudioStreamClip(sampleRate: number): StreamClip {
  const chunks: Float32Array[] = [];
  const sources: AudioBufferSourceNode[] = [];
  let playing = false;
  let stopped = false;
  let finished = false;
  let startAt = 0;
  let nextAt = 0;
  let totalSeconds = 0;
  let resolveEnded: () => void = () => undefined;
  const ended = new Promise<void>((r) => (resolveEnded = r));

  const endIfDrained = () => {
    if (finished && (sources.length === 0 || getAudioContext().currentTime >= nextAt - 0.01)) {
      resolveEnded();
    }
  };

  const schedule = (samples: Float32Array) => {
    const ctx = getAudioContext();
    const buffer = ctx.createBuffer(1, samples.length, sampleRate);
    buffer.copyToChannel(new Float32Array(samples), 0);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    // A late chunk (slow network) starts now instead of in the past.
    const at = Math.max(nextAt, ctx.currentTime);
    source.start(at);
    nextAt = at + buffer.duration;
    sources.push(source);
    source.onended = () => {
      sources.splice(sources.indexOf(source), 1);
      endIfDrained();
    };
  };

  return {
    push(samples) {
      if (stopped || samples.length === 0) return;
      totalSeconds += samples.length / sampleRate;
      if (playing) schedule(samples);
      else chunks.push(samples);
    },
    finish() {
      finished = true;
      if (playing) endIfDrained();
    },
    play(): Playback {
      const ctx = getAudioContext();
      if (ctx.state === "suspended") void ctx.resume().catch(() => undefined);
      playing = true;
      startAt = ctx.currentTime;
      nextAt = startAt;
      for (const samples of chunks.splice(0)) schedule(samples);
      if (finished) endIfDrained();
      return {
        ended,
        stop: () => {
          stopped = true;
          for (const source of sources.splice(0)) {
            source.onended = null;
            try {
              source.stop();
            } catch {
              // Already stopped.
            }
          }
          resolveEnded();
        },
        progress: () =>
          totalSeconds > 0 ? Math.min(1, (getAudioContext().currentTime - startAt) / totalSeconds) : 0,
      };
    },
  };
}

interface Pending {
  resolve: (clip: Clip) => void;
  reject: (error: Error) => void;
  clip: StreamClip | null;
}

export class OrpheusVoice implements Voice {
  readonly mode = "orpheus";
  readonly wholeTurns = true;
  private nextId = 1;
  private pending = new Map<number, Pending>();

  constructor(
    private readonly request: (id: number, text: string) => void,
    private readonly makeClip: ClipFactory = webAudioStreamClip,
  ) {}

  /** Resolves when the first audio arrives, so the player's first-audio timing is honest. */
  prepare(text: string): Promise<Clip> {
    const id = this.nextId++;
    return new Promise<Clip>((resolve, reject) => {
      this.pending.set(id, { resolve, reject, clip: null });
      this.request(id, text);
    });
  }

  /** Drop requests whose audio hasn't started (after an interruption). */
  cancelPending(): void {
    for (const [id, entry] of this.pending) {
      if (entry.clip === null) {
        entry.reject(new Error("cancelled"));
        this.pending.delete(id);
      }
    }
  }

  onAudio(id: number, sampleRate: number, pcm: ArrayBuffer): void {
    const entry = this.pending.get(id);
    if (!entry) return; // cancelled or unknown: ignore late frames
    if (entry.clip === null) {
      entry.clip = this.makeClip(sampleRate);
      entry.resolve(entry.clip);
    }
    entry.clip.push(pcm16ToFloat32(pcm));
  }

  onDone(id: number): void {
    const entry = this.pending.get(id);
    if (!entry) return;
    this.pending.delete(id);
    if (entry.clip) entry.clip.finish();
    else entry.reject(new Error("no audio"));
  }

  onFailed(id: number, code: string, message: string): void {
    const entry = this.pending.get(id);
    if (!entry) return;
    this.pending.delete(id);
    if (entry.clip) entry.clip.finish(); // keep what already played
    else entry.reject(new Error(`${code}: ${message}`));
  }
}

/**
 * Orpheus first; once it fails (daily limit, network), the backup voice speaks the rest of
 * the call, so Mia is never silent.
 */
export class FallbackVoice implements Voice {
  readonly wholeTurns = true;
  private failed = false;

  constructor(
    private readonly primary: Voice,
    private readonly backup: Voice,
    private readonly onFallback: (reason: string) => void = () => undefined,
  ) {}

  get mode(): Voice["mode"] {
    return this.failed ? this.backup.mode : this.primary.mode;
  }

  async prepare(text: string): Promise<Clip> {
    if (this.failed) return this.backup.prepare(text);
    try {
      return await this.primary.prepare(text);
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      if (reason === "cancelled") throw error;
      this.failed = true;
      this.onFallback(reason);
      return this.backup.prepare(text);
    }
  }

  cancelPending(): void {
    this.primary.cancelPending?.();
    this.backup.cancelPending?.();
  }
}
