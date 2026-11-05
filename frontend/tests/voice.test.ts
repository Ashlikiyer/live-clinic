import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { ORT_WEB_VERSION, VAD_WEB_VERSION } from "@/voice/vad";
import {
  SlowVoiceDetector,
  partialWords,
  playedText,
  shouldSendUtterance,
  shouldSwitchToKokoro,
} from "@/voice/turnTaking";
import { pickLiteVoice } from "@/voice/tts";
import { backendsToTry, isAudible } from "@/voice/ttsProtocol";
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

describe("pickLiteVoice", () => {
  const v = (name: string, lang = "en-US") => ({ name, lang });

  it("prefers a natural (neural) female English voice", () => {
    const aria = "Microsoft Aria Online (Natural) - English (United States)";
    const voices = [
      v("Microsoft David - English (United States)"),
      v("Microsoft Zira - English (United States)"),
      v(aria),
      v("Microsoft Guy Online (Natural) - English (United States)"),
    ];
    expect(pickLiteVoice(voices)?.name).toBe(aria);
  });

  it("never picks a known male voice", () => {
    const zira = "Microsoft Zira - English (United States)";
    const males = [v("Microsoft David - English (United States)"), v("Google UK English Male", "en-GB")];
    expect(pickLiteVoice(males)).toBeNull();
    expect(pickLiteVoice([...males, v(zira)])?.name).toBe(zira);
  });

  it("skips other languages and prefers US English", () => {
    const voices = [v("Google Deutsch", "de-DE"), v("Google UK English Female", "en-GB"), v("Google US English")];
    expect(pickLiteVoice(voices)?.name).toBe("Google US English");
  });

  it("prefers Chrome's Google voice over Windows' local Zira", () => {
    const voices = [v("Microsoft Zira - English (United States)"), v("Google US English")];
    expect(pickLiteVoice(voices)?.name).toBe("Google US English");
  });

  it("returns null when there are no voices yet", () => {
    expect(pickLiteVoice([])).toBeNull();
  });
});

describe("shouldSwitchToKokoro", () => {
  const base = { kokoroReady: true, downgraded: false, mode: "lite" as const, speaking: false };

  it("switches a lite call once Kokoro is ready, between replies", () => {
    expect(shouldSwitchToKokoro(base)).toBe(true);
  });

  it("waits while Kokoro loads or Mia talks, and never undoes a slow-device fallback", () => {
    expect(shouldSwitchToKokoro({ ...base, kokoroReady: false })).toBe(false);
    expect(shouldSwitchToKokoro({ ...base, speaking: true })).toBe(false);
    expect(shouldSwitchToKokoro({ ...base, downgraded: true })).toBe(false);
    expect(shouldSwitchToKokoro({ ...base, mode: "kokoro" })).toBe(false);
  });
});

describe("isAudible", () => {
  it("accepts voice-like audio (a 200 Hz tone at Kokoro's 24 kHz)", () => {
    const tone = Float32Array.from({ length: 2400 }, (_, i) => 0.4 * Math.sin((2 * Math.PI * 200 * i) / 24_000));
    expect(isAudible(tone)).toBe(true);
  });

  it("rejects silence, near-silence and NaN output", () => {
    expect(isAudible(new Float32Array(1000))).toBe(false);
    expect(isAudible(new Float32Array([0.001, -0.002]))).toBe(false);
    expect(isAudible(new Float32Array([0.3, Number.NaN, 0.2]))).toBe(false);
    expect(isAudible(new Float32Array([]))).toBe(false);
  });

  it("rejects static (noise that changes sign on almost every sample)", () => {
    const noise = Float32Array.from({ length: 2000 }, (_, i) => (i % 2 ? 0.4 : -0.4));
    expect(isAudible(noise)).toBe(false);
  });
});

describe("backendsToTry", () => {
  it("tries GPU half precision, then GPU full precision, then the CPU", () => {
    expect(backendsToTry({ device: "webgpu", dtype: "fp16" })).toEqual([
      { device: "webgpu", dtype: "fp16" },
      { device: "webgpu", dtype: "fp32" },
      { device: "wasm", dtype: "q8" },
    ]);
  });

  it("only tries the CPU on a device without a usable GPU", () => {
    expect(backendsToTry({ device: "wasm", dtype: "q8" })).toEqual([{ device: "wasm", dtype: "q8" }]);
  });
});
