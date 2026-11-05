/// <reference lib="webworker" />
/**
 * Kokoro TTS in a Web Worker so synthesis never blocks the UI thread.
 * Messages in: load | synth {id, text, gen} | cancel {gen}. Requests older than the latest
 * cancel generation are dropped, so an interruption doesn't leave stale audio queued.
 */

import { KokoroTTS } from "kokoro-js";

import {
  KEEP_GENERATION,
  KOKORO_MODEL,
  KOKORO_VOICE,
  WASM_BACKEND,
  backendsToTry,
  isAudible,
  type KokoroBackend,
  type WorkerIn,
  type WorkerOut,
} from "./ttsProtocol";

declare const self: DedicatedWorkerGlobalScope;

/** Minimal WebGPU typing; the DOM lib in this TypeScript setup doesn't include it. */
interface GpuLike {
  requestAdapter: () => Promise<{ features: { has: (f: string) => boolean } } | null>;
}

const BENCH_TEXT = "Sure, I can help with that.";

let tts: KokoroTTS | null = null;
let minGeneration = 0;

// One generation at a time (the ONNX session isn't re-entrant). Live speech always goes
// before background pre-generation, so a cached-phrase warm-up never delays a reply.
type Job = () => Promise<void>;
const urgent: Job[] = [];
const background: Job[] = [];
let running = false;

function schedule(): void {
  if (running) return;
  const job = urgent.shift() ?? background.shift();
  if (!job) return;
  running = true;
  void job().finally(() => {
    running = false;
    schedule();
  });
}

function enqueue(job: Job, priority: "urgent" | "background"): void {
  (priority === "urgent" ? urgent : background).push(job);
  schedule();
}

const fileProgress = new Map<string, { loaded: number; total: number }>();

function post(message: WorkerOut, transfer: Transferable[] = []): void {
  self.postMessage(message, transfer);
}

function reportProgress(info: unknown): void {
  const p = info as { status?: string; file?: string; loaded?: number; total?: number };
  if (p.status !== "progress" || !p.file || !p.total) return;
  fileProgress.set(p.file, { loaded: p.loaded ?? 0, total: p.total });
  let loaded = 0;
  let total = 0;
  for (const f of fileProgress.values()) {
    loaded += f.loaded;
    total += f.total;
  }
  post({ type: "progress", progress: total ? loaded / total : 0 });
}

async function preferredBackend(): Promise<KokoroBackend> {
  const gpu = (navigator as Navigator & { gpu?: GpuLike }).gpu;
  try {
    const adapter = await gpu?.requestAdapter();
    if (adapter?.features.has("shader-f16")) return { device: "webgpu", dtype: "fp16" };
  } catch {
    // No usable GPU: fall through to WASM.
  }
  return WASM_BACKEND;
}

async function loadWith(backend: KokoroBackend): Promise<KokoroTTS> {
  fileProgress.clear();
  return KokoroTTS.from_pretrained(KOKORO_MODEL, { ...backend, progress_callback: reportProgress });
}

/** Warm up, then time two runs and keep the faster (early runs compile kernels/shaders).
 * Returns the real-time factor, or null if the output isn't audible speech. */
async function benchmark(engine: KokoroTTS): Promise<number | null> {
  await engine.generate("Hi.", { voice: KOKORO_VOICE });
  let rtf = Infinity;
  for (let run = 0; run < 2; run++) {
    const started = performance.now();
    const sample = await engine.generate(BENCH_TEXT, { voice: KOKORO_VOICE });
    if (!isAudible(sample.audio as Float32Array)) return null;
    const audioMs = (sample.audio.length / sample.sampling_rate) * 1000;
    rtf = Math.min(rtf, (performance.now() - started) / audioMs);
  }
  return rtf;
}

async function load(): Promise<void> {
  // Try each backend until one loads and makes audible speech (see backendsToTry).
  const problems: string[] = [];
  for (const backend of backendsToTry(await preferredBackend())) {
    const label = `${backend.device} ${backend.dtype}`;
    try {
      tts = await loadWith(backend);
      const rtf = await benchmark(tts);
      if (rtf === null) {
        problems.push(`${label} made silent audio`);
        continue;
      }
      const note = problems.length
        ? `${problems.join("; ")}, so the voice runs on ${label}`
        : undefined;
      post({ type: "ready", device: backend.device, rtf, note });
      return;
    } catch (error) {
      problems.push(`${label} failed to load (${String(error)})`);
    }
  }
  tts = null;
  post({ type: "error", message: problems.join("; ") || "Kokoro couldn't load" });
}

const isStale = (gen: number) => gen !== KEEP_GENERATION && gen < minGeneration;

async function synth(id: number, text: string, gen: number): Promise<void> {
  if (!tts || isStale(gen)) {
    post({ type: "cancelled", id });
    return;
  }
  try {
    const result = await tts.generate(text, { voice: KOKORO_VOICE });
    if (isStale(gen)) {
      post({ type: "cancelled", id });
      return;
    }
    const audio = result.audio as Float32Array;
    if (!isAudible(audio)) {
      post({ type: "failed", id, message: `silent audio for "${text.slice(0, 40)}"` });
      return;
    }
    post({ type: "audio", id, audio, sampleRate: result.sampling_rate }, [audio.buffer]);
  } catch (error) {
    post({ type: "failed", id, message: String(error) });
  }
}

self.onmessage = (event: MessageEvent<WorkerIn>) => {
  const msg = event.data;
  if (msg.type === "load") {
    enqueue(load, "urgent");
  } else if (msg.type === "synth") {
    const priority = msg.gen === KEEP_GENERATION ? "background" : "urgent";
    enqueue(() => synth(msg.id, msg.text, msg.gen), priority);
  } else if (msg.type === "cancel") {
    minGeneration = msg.gen;
  }
};
