/** Messages between the page and the Kokoro worker, plus the model choice. */

export const KOKORO_MODEL = "onnx-community/Kokoro-82M-v1.0-ONNX";
// Nova: a warm, natural US English voice, picked by ear over the default "af_heart".
export const KOKORO_VOICE = "af_nova";

/**
 * Measured on an integrated GPU after warm-up: WebGPU fp16 ~0.5-0.6x real time (163 MB),
 * WASM q8 ~2.7x real time (92 MB). So WebGPU fp16 when the GPU supports it, else WASM q8.
 */
export type KokoroBackend =
  | { device: "webgpu"; dtype: "fp16" | "fp32" }
  | { device: "wasm"; dtype: "q8" };
export const WASM_BACKEND: KokoroBackend = { device: "wasm", dtype: "q8" };

/**
 * Backends to try, best first. Some GPUs make silent (NaN) audio in half precision; full
 * precision still runs on the GPU and fixes that, at the cost of a bigger one-time download
 * (~326 MB vs 163 MB) that only those devices make. The CPU (WASM) path is the last resort.
 */
export function backendsToTry(first: KokoroBackend): KokoroBackend[] {
  if (first.device === "wasm") return [WASM_BACKEND];
  const candidates: KokoroBackend[] = [first, { device: "webgpu", dtype: "fp32" }, WASM_BACKEND];
  return candidates.filter(
    (b, i, all) => all.findIndex((o) => o.device === b.device && o.dtype === b.dtype) === i,
  );
}

/** Never cancelled by an interruption (used for pre-generated phrases). */
export const KEEP_GENERATION = -1;

/** Loudest sample a real spoken sentence reaches at the very least (Kokoro peaks ~0.3-0.6). */
const MIN_SPEECH_PEAK = 0.01;
/**
 * Share of samples where the waveform changes sign. Measured Kokoro speech: 0.13-0.28; white
 * noise: 0.5. Above this it is static, not a voice.
 */
const MAX_SPEECH_ZERO_CROSSINGS = 0.4;

/**
 * Is this generated audio real speech? On some GPUs WebGPU makes NaN or all-zero samples
 * (heard as silence) or garbage (heard as static), while everything else looks fine. Pure.
 */
export function isAudible(samples: ArrayLike<number>): boolean {
  let peak = 0;
  let crossings = 0;
  for (let i = 0; i < samples.length; i++) {
    const s = samples[i];
    if (!Number.isFinite(s)) return false;
    peak = Math.max(peak, Math.abs(s));
    if (i > 0 && samples[i - 1] >= 0 !== s >= 0) crossings += 1;
  }
  return peak >= MIN_SPEECH_PEAK && crossings / samples.length <= MAX_SPEECH_ZERO_CROSSINGS;
}

export type WorkerIn =
  | { type: "load" }
  | { type: "synth"; id: number; text: string; gen: number }
  | { type: "cancel"; gen: number };

export type WorkerOut =
  | { type: "progress"; progress: number }
  | { type: "ready"; device: KokoroBackend["device"]; rtf: number; note?: string }
  | { type: "error"; message: string }
  | { type: "audio"; id: number; audio: Float32Array; sampleRate: number }
  | { type: "cancelled"; id: number }
  | { type: "failed"; id: number; message: string };
