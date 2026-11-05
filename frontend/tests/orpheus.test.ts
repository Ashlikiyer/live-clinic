import { describe, expect, it, vi } from "vitest";

import { FallbackVoice, OrpheusVoice, pcm16ToFloat32, type StreamClip } from "@/voice/orpheus";
import { SentencePlayer, type Clip, type Voice } from "@/voice/player";
import { buildAudioFrame, parseAudioFrame } from "@/voice/wav";

/** A clip that records what it was given instead of playing it. */
function fakeClip(): StreamClip & { pushed: number; finished: boolean } {
  const clip = {
    pushed: 0,
    finished: false,
    push(samples: Float32Array) {
      clip.pushed += samples.length;
    },
    finish() {
      clip.finished = true;
    },
    play: () => ({ ended: Promise.resolve(), stop: () => undefined, progress: () => 1 }),
  };
  return clip;
}

const pcm = (...samples: number[]) => new Int16Array(samples).buffer;

describe("pcm16ToFloat32", () => {
  it("scales 16-bit samples to -1..1", () => {
    expect(Array.from(pcm16ToFloat32(pcm(0, 16384, -32768, 32767)))).toEqual([
      0,
      0.5,
      -1,
      32767 / 32768,
    ]);
  });

  it("ignores a trailing half sample", () => {
    expect(pcm16ToFloat32(new Uint8Array([0, 64, 1]).buffer)).toHaveLength(1);
  });
});

describe("parseAudioFrame", () => {
  it("reads the server's tts.audio frames", () => {
    const header = { type: "tts.audio", id: 3, seq: 0, sample_rate: 24_000 };
    // buildAudioFrame is typed for the caller's audio header; the layout is the same.
    const frame = buildAudioFrame(header as never, pcm(1, 2));
    const parsed = parseAudioFrame(frame);
    expect(parsed?.header).toEqual(header);
    expect(Array.from(new Int16Array(parsed!.payload))).toEqual([1, 2]);
  });

  it("rejects broken frames", () => {
    expect(parseAudioFrame(new ArrayBuffer(2))).toBeNull();
    const lying = new Uint8Array([0, 0, 0, 99, 123]).buffer; // header longer than the frame
    expect(parseAudioFrame(lying)).toBeNull();
  });
});

describe("OrpheusVoice", () => {
  function setup() {
    const requests: { id: number; text: string }[] = [];
    const clips: ReturnType<typeof fakeClip>[] = [];
    const voice = new OrpheusVoice(
      (id, text) => requests.push({ id, text }),
      () => {
        const clip = fakeClip();
        clips.push(clip);
        return clip;
      },
    );
    return { voice, requests, clips };
  }

  it("asks the server, resolves at the first audio, and streams the rest into the clip", async () => {
    const { voice, requests, clips } = setup();
    const ready = voice.prepare("Sure. See you Friday.");
    expect(requests).toEqual([{ id: 1, text: "Sure. See you Friday." }]);
    voice.onAudio(1, 24_000, pcm(1, 2, 3));
    await expect(ready).resolves.toBe(clips[0]);
    voice.onAudio(1, 24_000, pcm(4));
    voice.onDone(1);
    expect(clips[0].pushed).toBe(4);
    expect(clips[0].finished).toBe(true);
    voice.onAudio(1, 24_000, pcm(9)); // late frame after done: ignored
    expect(clips[0].pushed).toBe(4);
  });

  it("rejects when the server can't speak the line", async () => {
    const { voice } = setup();
    const ready = voice.prepare("Hi.");
    voice.onFailed(1, "RATE_LIMITED", "Busy right now");
    await expect(ready).rejects.toThrow("RATE_LIMITED: Busy right now");
  });

  it("drops requests that haven't started when the caller interrupts", async () => {
    const { voice, clips } = setup();
    const playing = voice.prepare("First.");
    voice.onAudio(1, 24_000, pcm(1));
    const waiting = voice.prepare("Second.");
    voice.cancelPending();
    await expect(waiting).rejects.toThrow("cancelled");
    await expect(playing).resolves.toBe(clips[0]); // already playing: left to the player
    voice.onAudio(2, 24_000, pcm(1)); // the cancelled request's audio: ignored
    expect(clips).toHaveLength(1);
  });
});

describe("FallbackVoice", () => {
  const clip: Clip = { play: () => ({ ended: Promise.resolve(), stop: () => undefined, progress: () => 1 }) };

  function voices(primaryFails: string | null) {
    const primary: Voice = {
      mode: "orpheus",
      prepare: vi.fn(() => (primaryFails ? Promise.reject(new Error(primaryFails)) : Promise.resolve(clip))),
    };
    const backup: Voice = { mode: "lite", prepare: vi.fn(() => Promise.resolve(clip)) };
    const onFallback = vi.fn();
    return { primary, backup, onFallback, voice: new FallbackVoice(primary, backup, onFallback) };
  }

  it("uses Orpheus while it works", async () => {
    const { voice, backup } = voices(null);
    await voice.prepare("Hi.");
    expect(voice.mode).toBe("orpheus");
    expect(backup.prepare).not.toHaveBeenCalled();
  });

  it("switches to the built-in voice for the rest of the call once Orpheus fails", async () => {
    const { voice, primary, backup, onFallback } = voices("RATE_LIMITED: Busy");
    await expect(voice.prepare("Hi.")).resolves.toBe(clip);
    await voice.prepare("Still there?");
    expect(voice.mode).toBe("lite");
    expect(onFallback).toHaveBeenCalledOnce();
    expect(primary.prepare).toHaveBeenCalledOnce();
    expect(backup.prepare).toHaveBeenCalledTimes(2);
  });

  it("doesn't fall back for an interruption", async () => {
    const { voice, onFallback } = voices("cancelled");
    await expect(voice.prepare("Hi.")).rejects.toThrow("cancelled");
    expect(onFallback).not.toHaveBeenCalled();
    expect(voice.mode).toBe("orpheus");
  });
});

describe("SentencePlayer with a whole-reply voice", () => {
  it("speaks the reply as one piece (no comma split, one request)", () => {
    const texts: string[] = [];
    const voice: Voice = {
      mode: "orpheus",
      wholeTurns: true,
      prepare: (text) => {
        texts.push(text);
        return new Promise<Clip>(() => undefined);
      },
    };
    new SentencePlayer(voice).enqueue(1, 0, "Sure, I can help with that. What day works?");
    expect(texts).toEqual(["Sure, I can help with that. What day works?"]);
  });
});
