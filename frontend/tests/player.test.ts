import { describe, expect, it, vi } from "vitest";

import { SentencePlayer, type Clip, type Playback, type Voice } from "@/voice/player";

/** A fake voice whose synthesis and playback the test finishes by hand. */
class FakeVoice implements Voice {
  readonly mode = "kokoro";
  synth: { text: string; resolve: (c: Clip) => void }[] = [];
  playing: { text: string; finish: () => void; progress: number; stopped: boolean }[] = [];
  cancelled = 0;

  prepare(text: string): Promise<Clip> {
    return new Promise<Clip>((resolve) => this.synth.push({ text, resolve }));
  }

  cancelPending(): void {
    this.cancelled += 1;
  }

  /** Finish synthesizing the queued sentence with this text. */
  ready(text: string): void {
    const job = this.synth.find((s) => s.text === text)!;
    job.resolve({
      play: (): Playback => {
        let finish!: () => void;
        const ended = new Promise<void>((r) => (finish = r));
        const entry = { text, finish, progress: 0, stopped: false };
        this.playing.push(entry);
        return {
          ended,
          stop: () => {
            entry.stopped = true;
            finish();
          },
          progress: () => entry.progress,
        };
      },
    });
  }

  current() {
    return this.playing.at(-1)!;
  }
}

const tick = () => new Promise((r) => setTimeout(r, 0));

function setup() {
  const voice = new FakeVoice();
  const log: string[] = [];
  let clock = 0;
  const player = new SentencePlayer(
    voice,
    {
      onSpeakingChange: (s) => log.push(s ? "speaking" : "silent"),
      onFirstAudio: (turn, ms) => log.push(`first-audio ${turn} ${ms}`),
    },
    () => clock,
  );
  return { voice, player, log, advance: (ms: number) => (clock += ms) };
}

describe("SentencePlayer", () => {
  it("plays sentences in index order even if synthesis finishes out of order", async () => {
    const { voice, player, log, advance } = setup();
    player.enqueue(1, 0, "First.");
    player.enqueue(1, 1, "Second.");
    advance(180);
    voice.ready("Second.");
    await tick();
    expect(voice.playing).toEqual([]);
    voice.ready("First.");
    await tick();
    expect(voice.current().text).toBe("First.");
    expect(log).toContain("first-audio 1 180");
    voice.current().finish();
    await tick();
    expect(voice.current().text).toBe("Second.");
  });

  it("stays speaking between sentences until the turn's text is done and played", async () => {
    const { voice, player, log } = setup();
    player.enqueue(1, 0, "One.");
    voice.ready("One.");
    await tick();
    voice.current().finish();
    await tick();
    expect(player.isSpeaking).toBe(true);
    player.enqueue(1, 1, "Two.");
    voice.ready("Two.");
    await tick();
    player.markDone(1);
    voice.current().finish();
    await tick();
    expect(player.isSpeaking).toBe(false);
    expect(log.filter((l) => l === "speaking")).toHaveLength(1);
  });

  it("stop() cuts audio and reports only what was heard", async () => {
    const { voice, player, advance } = setup();
    player.enqueue(2, 0, "Sure.");
    player.enqueue(2, 1, "I am holding Wednesday at nine thirty for you.");
    voice.ready("Sure.");
    await tick();
    voice.current().finish();
    voice.ready("I am holding Wednesday at nine thirty for you.");
    await tick();
    voice.current().progress = 0.4;
    advance(1200);
    const cancelsBefore = voice.cancelled;

    const result = player.stop();
    expect(result).toEqual({
      turnId: 2,
      playedText: "Sure. I am holding", // 40% of 9 words, rounded down
      playedMs: 1200,
    });
    expect(voice.current().stopped).toBe(true);
    expect(voice.cancelled).toBe(cancelsBefore + 1); // queued synthesis is dropped
    expect(player.isSpeaking).toBe(false);
  });

  it("ignores late sentences for an interrupted turn and for older turns", async () => {
    const { voice, player } = setup();
    player.enqueue(3, 0, "Hello.");
    player.stop();
    player.enqueue(3, 1, "Late sentence.");
    player.enqueue(2, 0, "Old turn.");
    expect(voice.synth.map((s) => s.text)).toEqual(["Hello."]);
    voice.ready("Hello.");
    await tick();
    expect(voice.playing).toEqual([]);
  });

  it("a newer turn replaces the old one", async () => {
    const { voice, player } = setup();
    player.enqueue(1, 0, "Old.");
    player.enqueue(2, 0, "New.");
    voice.ready("Old.");
    voice.ready("New.");
    await tick();
    await tick();
    expect(voice.playing.map((p) => p.text)).toEqual(["New."]);
  });

  it("plays the first sentence in two pieces, split at its first comma", async () => {
    const { voice, player } = setup();
    player.enqueue(1, 0, "Sure, I can help with that today.");
    player.enqueue(1, 1, "Which day?");
    expect(voice.synth.map((s) => s.text)).toEqual(["Sure,", "I can help with that today.", "Which day?"]);
    voice.ready("Which day?");
    voice.ready("Sure,");
    await tick();
    expect(voice.current().text).toBe("Sure,");
    voice.current().finish();
    voice.ready("I can help with that today.");
    await tick();
    expect(voice.current().text).toBe("I can help with that today.");
    voice.current().progress = 0.5;
    expect(player.stop()?.playedText).toBe("Sure, I can help");
  });

  it("stop() before any audio reports nothing", () => {
    const { player } = setup();
    player.enqueue(1, 0, "Hi.");
    expect(player.stop()).toBeNull();
  });
});

describe("SentencePlayer with a failing voice", () => {
  it("reports a sentence it couldn't synthesize and plays the next one", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const voice = new FakeVoice();
    const failing: Voice = {
      mode: "kokoro",
      prepare: (text) =>
        text === "Broken." ? Promise.reject(new Error("voice file missing")) : voice.prepare(text),
      cancelPending: () => undefined,
    };
    const player = new SentencePlayer(failing);
    player.enqueue(1, 0, "Broken.");
    player.enqueue(1, 1, "This one works.");
    await tick();
    voice.ready("This one works.");
    await tick();
    expect(voice.current().text).toBe("This one works.");
    expect(warn).toHaveBeenCalledWith("[voice] couldn't synthesize a sentence: voice file missing");
    warn.mockRestore();
  });

  it("stays quiet about sentences cancelled by an interruption", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const cancelled: Voice = {
      mode: "kokoro",
      prepare: () => Promise.reject(new Error("cancelled")),
      cancelPending: () => undefined,
    };
    new SentencePlayer(cancelled).enqueue(1, 0, "Gone.");
    await tick();
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});
