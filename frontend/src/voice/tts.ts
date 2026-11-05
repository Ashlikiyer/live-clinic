/**
 * Voices: Kokoro (natural, runs in a worker) and the browser's speechSynthesis ("lite",
 * zero download). Kokoro loads once per page and is warmed up before the first call.
 */

import type { KokoroState } from "./choice";
import { phraseKey, precachePieces } from "./phrases";
import type { Clip, Playback, Voice } from "./player";
import { KEEP_GENERATION, type KokoroBackend, type WorkerIn, type WorkerOut } from "./ttsProtocol";

/**
 * Up-front speed check: well past real time (e.g. CPU-only WASM, ~2.7x) can't keep up, so use
 * the lite voice. Borderline devices keep Kokoro: openers are cached, and the runtime rule
 * (two slow first-audio starts in a row) still switches to lite mid-call if needed.
 */
export const MAX_KOKORO_RTF = 1.5;

let audioContext: AudioContext | null = null;

/** Shared output context. Call `resumeAudio()` from a click so autoplay rules allow sound. */
export function getAudioContext(): AudioContext {
  audioContext ??= new AudioContext();
  return audioContext;
}

export async function resumeAudio(): Promise<void> {
  const ctx = getAudioContext();
  if (ctx.state === "suspended") await ctx.resume();
}

function bufferClip(samples: Float32Array, sampleRate: number): Clip {
  return {
    play(): Playback {
      const ctx = getAudioContext();
      // A suspended context (autoplay rules, a dev hot reload) would "play" in silence.
      if (ctx.state === "suspended") void ctx.resume().catch(() => undefined);
      const buffer = ctx.createBuffer(1, samples.length, sampleRate);
      buffer.copyToChannel(new Float32Array(samples), 0);
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(ctx.destination);
      let resolve!: () => void;
      const ended = new Promise<void>((r) => (resolve = r));
      source.onended = () => resolve();
      const startedAt = ctx.currentTime;
      source.start();
      return {
        ended,
        stop: () => {
          source.onended = null;
          try {
            source.stop();
          } catch {
            // Already stopped.
          }
          resolve();
        },
        progress: () => Math.min(1, (ctx.currentTime - startedAt) / buffer.duration),
      };
    },
  };
}

// ---------- Kokoro ----------

export type KokoroStatus =
  | { state: "loading"; progress: number }
  | { state: "ready"; device: KokoroBackend["device"]; rtf: number; tooSlow: boolean }
  | { state: "failed"; message: string };

class KokoroVoice implements Voice {
  readonly mode = "kokoro";
  private nextId = 1;
  private generation = 0;
  private pending = new Map<number, { resolve: (c: Clip) => void; reject: (e: Error) => void }>();
  /** Pre-generated fixed phrases (greeting, recovery lines), reused on every call. */
  private cache = new Map<string, { clip: Promise<Clip>; ready: boolean }>();

  constructor(private readonly worker: Worker) {
    worker.addEventListener("message", (event: MessageEvent<WorkerOut>) => {
      const msg = event.data;
      if (msg.type !== "audio" && msg.type !== "cancelled" && msg.type !== "failed") return;
      const waiter = this.pending.get(msg.id);
      if (!waiter) return;
      this.pending.delete(msg.id);
      if (msg.type === "audio") waiter.resolve(bufferClip(msg.audio, msg.sampleRate));
      else waiter.reject(new Error(msg.type === "failed" ? msg.message : "cancelled"));
    });
  }

  prepare(text: string): Promise<Clip> {
    const cached = this.cache.get(phraseKey(text));
    // A phrase still waiting in the background queue is synthesized now, at full priority.
    return cached?.ready ? cached.clip : this.synth(text, this.generation);
  }

  precache(texts: string[]): void {
    for (const text of texts) {
      const key = phraseKey(text);
      if (!this.cache.has(key)) {
        const entry = { clip: this.synth(text, KEEP_GENERATION), ready: false };
        entry.clip.then(
          () => (entry.ready = true),
          () => this.cache.delete(key),
        );
        this.cache.set(key, entry);
      }
    }
  }

  private synth(text: string, gen: number): Promise<Clip> {
    const id = this.nextId++;
    return new Promise<Clip>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.send({ type: "synth", id, text, gen });
    });
  }

  cancelPending(): void {
    this.generation += 1;
    this.send({ type: "cancel", gen: this.generation });
  }

  private send(msg: WorkerIn): void {
    this.worker.postMessage(msg);
  }
}

let kokoro: Promise<Voice> | null = null;
const statusListeners = new Set<(s: KokoroStatus) => void>();
let lastStatus: KokoroStatus = { state: "loading", progress: 0 };

function emit(status: KokoroStatus): void {
  lastStatus = status;
  statusListeners.forEach((listener) => listener(status));
}

/** Start (once) downloading and warming up Kokoro. Resolves when it can speak. */
export function loadKokoro(): Promise<Voice> {
  kokoro ??= new Promise<Voice>((resolve, reject) => {
    const worker = new Worker(new URL("./tts.worker.ts", import.meta.url), { type: "module" });
    worker.addEventListener("message", (event: MessageEvent<WorkerOut>) => {
      const msg = event.data;
      if (msg.type === "progress") emit({ state: "loading", progress: msg.progress });
      else if (msg.type === "ready") {
        const voice = new KokoroVoice(worker);
        voice.precache(precachePieces());
        emit({ state: "ready", device: msg.device, rtf: msg.rtf, tooSlow: msg.rtf > MAX_KOKORO_RTF });
        console.info(`[voice] Kokoro on ${msg.device}, ${msg.rtf.toFixed(2)}x real time`);
        if (msg.note) console.warn(`[voice] ${msg.note}`);
        resolve(voice);
      } else if (msg.type === "error") {
        emit({ state: "failed", message: msg.message });
        reject(new Error(msg.message));
      }
    });
    worker.addEventListener("error", (event) => {
      emit({ state: "failed", message: event.message });
      reject(new Error(event.message));
    });
    worker.postMessage({ type: "load" } satisfies WorkerIn);
  });
  return kokoro;
}

/** Kokoro's state for planVoice: "idle" until something asks for it. */
export function kokoroState(): KokoroState {
  if (kokoro === null) return "idle";
  if (lastStatus.state === "ready") return lastStatus.tooSlow ? "too_slow" : "ready";
  return lastStatus.state;
}

/** Use Kokoro for the next call? Only once loaded, and only if this device keeps up. */
export function kokoroPreferred(): boolean {
  return lastStatus.state === "ready" && !lastStatus.tooSlow;
}

export function onKokoroStatus(listener: (s: KokoroStatus) => void): () => void {
  statusListeners.add(listener);
  listener(lastStatus);
  return () => statusListeners.delete(listener);
}

// ---------- Lite (speechSynthesis) ----------

const LITE_MS_PER_CHAR = 65;

/** What pickLiteVoice needs from a browser voice (a SpeechSynthesisVoice fits). */
export interface VoiceInfo {
  name: string;
  lang: string;
}

// Neural voices (Edge's "Microsoft Aria Online (Natural)") sound close to human; the plain
// system voices sound robotic. Mia is a woman, so known male voices are never picked.
// Google's voices in Chrome are network voices too, far less robotic than Windows' local ones.
const NATURAL = /natural|online|neural|premium|enhanced|google/i;
const FEMALE =
  /\b(aria|jenny|ava|emma|michelle|ana|sonia|libby|natasha|clara|samantha|zira|susan|hazel|karen|moira|tessa|victoria|female)\b|google us english/i;
const MALE =
  /\b(david|mark|guy|andrew|brian|christopher|eric|roger|steffan|ryan|william|george|james|daniel|alex|fred|tom|male)\b/i;

/** The most natural English female voice on this device, or null to use the default. */
export function pickLiteVoice<V extends VoiceInfo>(voices: readonly V[]): V | null {
  let best: V | null = null;
  let bestScore = -Infinity;
  for (const voice of voices) {
    if (!voice.lang.toLowerCase().startsWith("en") || MALE.test(voice.name)) continue;
    const score =
      (NATURAL.test(voice.name) ? 100 : 0) +
      (FEMALE.test(voice.name) ? 50 : 0) +
      (voice.lang.toLowerCase() === "en-us" ? 10 : 0);
    if (score > bestScore) {
      best = voice;
      bestScore = score;
    }
  }
  return best;
}

let loggedLiteVoice = "";

function logLiteVoice(name: string): void {
  if (name === loggedLiteVoice) return;
  loggedLiteVoice = name;
  console.info(`[voice] built-in voice: ${name}`);
}

export class LiteVoice implements Voice {
  readonly mode = "lite";

  static available(): boolean {
    return typeof window !== "undefined" && "speechSynthesis" in window;
  }

  constructor() {
    // Some browsers fill the voice list asynchronously; asking early starts that.
    if (LiteVoice.available()) window.speechSynthesis.getVoices();
  }

  async prepare(text: string): Promise<Clip> {
    return {
      play: (): Playback => {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "en-US";
        const voice = pickLiteVoice(window.speechSynthesis.getVoices());
        logLiteVoice(voice?.name ?? "browser default");
        if (voice) {
          utterance.voice = voice;
          utterance.lang = voice.lang;
        }
        utterance.rate = 1.05;
        let spokenChars = 0;
        let resolve!: () => void;
        const ended = new Promise<void>((r) => (resolve = r));
        utterance.onend = () => resolve();
        utterance.onerror = (e) => {
          if (e.error !== "interrupted" && e.error !== "canceled") {
            console.warn(`[voice] built-in voice failed: ${e.error}`);
          }
          resolve();
        };
        utterance.onboundary = (e) => (spokenChars = e.charIndex);
        const startedAt = performance.now();
        window.speechSynthesis.speak(utterance);
        return {
          ended,
          stop: () => {
            window.speechSynthesis.cancel();
            resolve();
          },
          progress: () => {
            if (spokenChars > 0) return spokenChars / text.length;
            return Math.min(1, (performance.now() - startedAt) / (text.length * LITE_MS_PER_CHAR));
          },
        };
      },
    };
  }

  cancelPending(): void {
    window.speechSynthesis.cancel();
  }
}
