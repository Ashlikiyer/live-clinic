/** Messages between the page and the Kokoro worker, plus the model choice. */

export const KOKORO_MODEL = "onnx-community/Kokoro-82M-v1.0-ONNX";
export const KOKORO_VOICE = "af_heart";

/**
 * Measured on an integrated GPU after warm-up: WebGPU fp16 ~0.5-0.6x real time (163 MB),
 * WASM q8 ~2.7x real time (92 MB). So WebGPU fp16 when the GPU supports it, else WASM q8.
 */
export type KokoroBackend = { device: "webgpu"; dtype: "fp16" } | { device: "wasm"; dtype: "q8" };
export const WASM_BACKEND: KokoroBackend = { device: "wasm", dtype: "q8" };

/** Never cancelled by an interruption (used for pre-generated phrases). */
export const KEEP_GENERATION = -1;

export type WorkerIn =
  | { type: "load" }
  | { type: "synth"; id: number; text: string; gen: number }
  | { type: "cancel"; gen: number };

export type WorkerOut =
  | { type: "progress"; progress: number }
  | { type: "ready"; device: KokoroBackend["device"]; rtf: number }
  | { type: "error"; message: string }
  | { type: "audio"; id: number; audio: Float32Array; sampleRate: number }
  | { type: "cancelled"; id: number }
  | { type: "failed"; id: number; message: string };
