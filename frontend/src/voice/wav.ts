/** Float32 samples -> 16-bit PCM WAV, and the binary frame format sent to /ws/call. */

import type { AudioUtteranceHeader } from "@/realtime/events";

export const VAD_SAMPLE_RATE = 16_000;

export function encodeWav(samples: Float32Array, sampleRate = VAD_SAMPLE_RATE): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeAscii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };

  writeAscii(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeAscii(8, "WAVE");
  writeAscii(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeAscii(36, "data");
  view.setUint32(40, samples.length * 2, true);

  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

/** 4-byte big-endian header length + JSON header + WAV bytes. */
export function buildAudioFrame(header: AudioUtteranceHeader, wav: ArrayBuffer): ArrayBuffer {
  const json = new TextEncoder().encode(JSON.stringify(header));
  const frame = new Uint8Array(4 + json.length + wav.byteLength);
  new DataView(frame.buffer).setUint32(0, json.length, false);
  frame.set(json, 4);
  frame.set(new Uint8Array(wav), 4 + json.length);
  return frame.buffer;
}

/** Root-mean-square level of a frame, scaled to roughly 0..1 for the mic meter. */
export function rmsLevel(frame: Float32Array): number {
  if (frame.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
  return Math.min(1, Math.sqrt(sum / frame.length) * 6);
}
