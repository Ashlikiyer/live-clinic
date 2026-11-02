import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { ORT_WEB_VERSION, VAD_WEB_VERSION } from "@/voice/vad";
import {
  SlowVoiceDetector,
  partialWords,
  playedText,
  shouldSendUtterance,
} from "@/voice/turnTaking";
import { buildAudioFrame, encodeWav, rmsLevel } from "@/voice/wav";

describe("encodeWav", () => {
  it("writes a 16 kHz mono 16-bit PCM WAV", () => {
    const wav = encodeWav(new Float32Array([0, 1, -1, 0.5]));
    const view = new DataView(wav);
    const ascii = (o: number) => String.fromCharCode(...new Uint8Array(wav, o, 4));
    expect(ascii(0)).toBe("RIFF");
    expect(ascii(8)).toBe("WAVE");
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(16_000);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getUint32(40, true)).toBe(8);
    expect(wav.byteLength).toBe(44 + 8);
    expect(view.getInt16(46, true)).toBe(0x7fff);
    expect(view.getInt16(48, true)).toBe(-0x8000);
  });

  it("clips samples outside -1..1", () => {
    const view = new DataView(encodeWav(new Float32Array([3, -3])));
    expect(view.getInt16(44, true)).toBe(0x7fff);
    expect(view.getInt16(46, true)).toBe(-0x8000);
  });
});

describe("buildAudioFrame", () => {
  it("prefixes a big-endian header length and JSON header", () => {
    const header = { type: "audio.utterance", turn_id: 3, speech_end_ts: 42 } as const;
    const frame = buildAudioFrame(header, new Uint8Array([9, 8, 7]).buffer);
    const view = new DataView(frame);
    const length = view.getUint32(0, false);
    const json = new TextDecoder().decode(new Uint8Array(frame, 4, length));
    expect(JSON.parse(json)).toEqual(header);
    expect([...new Uint8Array(frame, 4 + length)]).toEqual([9, 8, 7]);
  });
});

describe("turn-taking rules", () => {
  it("ignores short sounds while the agent talks, keeps everything else", () => {
    expect(shouldSendUtterance({ agentSpeakingAtStart: false, bargedIn: false })).toBe(true);
    expect(shouldSendUtterance({ agentSpeakingAtStart: true, bargedIn: true })).toBe(true);
    expect(shouldSendUtterance({ agentSpeakingAtStart: true, bargedIn: false })).toBe(false);
  });

  it("reports the words actually heard", () => {
    expect(partialWords("one two three four", 0.5)).toBe("one two");
    expect(partialWords("one two", 0)).toBe("");
    expect(playedText(["Sure."], "I can hold Wednesday for you.", 0.4)).toBe("Sure. I can");
    expect(playedText([], null, 1)).toBe("");
  });

  it("falls back to the lite voice after two slow starts in a row", () => {
    const detector = new SlowVoiceDetector();
    expect(detector.record(1600)).toBe(false);
    expect(detector.record(900)).toBe(false);
    expect(detector.record(1600)).toBe(false);
    expect(detector.record(1700)).toBe(true);
  });

  it("scales the mic level", () => {
    expect(rmsLevel(new Float32Array(0))).toBe(0);
    expect(rmsLevel(new Float32Array([1, -1]))).toBe(1);
  });
});

describe("VAD asset versions", () => {
  it("match the installed packages, so CDN assets fit the bundled code", () => {
    const version = (pkg: string) =>
      (JSON.parse(readFileSync(`node_modules/${pkg}/package.json`, "utf8")) as { version: string })
        .version;
    expect(VAD_WEB_VERSION).toBe(version("@ricky0123/vad-web"));
    expect(ORT_WEB_VERSION).toBe(version("onnxruntime-web"));
  });
});
