/**
 * Silero VAD in the browser (@ricky0123/vad-web). Detects when the caller starts and stops
 * speaking and returns each utterance as 16 kHz audio. Barge-in timing lives in the caller.
 */

import { END_SILENCE_MS } from "./turnTaking";
import { rmsLevel } from "./wav";

/** Pinned to the installed package versions (checked by a unit test). */
export const VAD_WEB_VERSION = "0.0.31";
export const ORT_WEB_VERSION = "1.31.1";
const VAD_ASSETS = `https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@${VAD_WEB_VERSION}/dist/`;
const ORT_ASSETS = `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_WEB_VERSION}/dist/`;

export interface SpeechEndInfo {
  /** Browser epoch ms of the last voiced audio. */
  speechEndTs: number;
  /** Silence the VAD waited for before deciding the caller was done. */
  vadWaitMs: number;
  /** How long the caller actually spoke. */
  speechMs: number;
}

export interface MicCallbacks {
  onSpeechStart: () => void;
  onSpeechEnd: (audio: Float32Array, info: SpeechEndInfo) => void;
  onMisfire: () => void;
  onLevel: (level: number) => void;
}

export interface Mic {
  pause: () => Promise<void>;
  resume: () => Promise<void>;
  destroy: () => Promise<void>;
}

export class MicError extends Error {
  constructor(
    readonly reason: "denied" | "unavailable",
    message: string,
  ) {
    super(message);
  }
}

const AUDIO_CONSTRAINTS: MediaTrackConstraints = {
  channelCount: 1,
  // The browser's echo cancellation keeps the agent's voice from triggering barge-in.
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
};

async function requestPermission(): Promise<void> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new MicError("unavailable", "This browser can't use a microphone here.");
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: AUDIO_CONSTRAINTS });
    stream.getTracks().forEach((t) => t.stop());
  } catch (error) {
    const name = error instanceof DOMException ? error.name : "";
    if (name === "NotAllowedError" || name === "SecurityError") {
      throw new MicError("denied", "Microphone permission was denied.");
    }
    throw new MicError("unavailable", "No microphone was found.");
  }
}

export async function startMic(callbacks: MicCallbacks): Promise<Mic> {
  await requestPermission();
  const { MicVAD } = await import("@ricky0123/vad-web");

  let speechStartedAt = 0;
  let lastLevelAt = 0;
  const vad = await MicVAD.new({
    model: "v5",
    baseAssetPath: VAD_ASSETS,
    onnxWASMBasePath: ORT_ASSETS,
    redemptionMs: END_SILENCE_MS,
    minSpeechMs: 250,
    preSpeechPadMs: 300,
    positiveSpeechThreshold: 0.5,
    negativeSpeechThreshold: 0.35,
    startOnLoad: true,
    getStream: () => navigator.mediaDevices.getUserMedia({ audio: AUDIO_CONSTRAINTS }),
    onSpeechStart: () => {
      speechStartedAt = performance.now();
      callbacks.onSpeechStart();
    },
    onVADMisfire: () => callbacks.onMisfire(),
    onSpeechEnd: (audio) => {
      const now = Date.now();
      callbacks.onSpeechEnd(audio, {
        speechEndTs: now - END_SILENCE_MS,
        vadWaitMs: END_SILENCE_MS,
        speechMs: Math.max(0, performance.now() - speechStartedAt - END_SILENCE_MS),
      });
    },
    onFrameProcessed: (_probabilities, frame) => {
      const t = performance.now();
      if (t - lastLevelAt > 80) {
        lastLevelAt = t;
        callbacks.onLevel(rmsLevel(frame));
      }
    },
  });
  if (vad.errored) throw new MicError("unavailable", vad.errored);

  return {
    pause: () => vad.pause(),
    resume: () => vad.start(),
    destroy: () => vad.destroy(),
  };
}
