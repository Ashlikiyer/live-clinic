import { describe, expect, it } from "vitest";

import { DEFAULT_VOICE, parseVoiceChoice, planVoice } from "@/voice/choice";

describe("planVoice", () => {
  it("uses Groq Orpheus by default, on any device", () => {
    expect(DEFAULT_VOICE).toBe("orpheus");
    expect(planVoice("orpheus", "idle", true)).toEqual({ kind: "orpheus" });
  });

  it("uses Kokoro only once it's ready, and the built-in voice until then", () => {
    expect(planVoice("kokoro", "ready", true)).toEqual({ kind: "kokoro" });
    expect(planVoice("kokoro", "loading", true)).toEqual({ kind: "lite", waitForKokoro: true });
    expect(planVoice("kokoro", "too_slow", true)).toEqual({ kind: "lite", waitForKokoro: false });
    expect(planVoice("kokoro", "failed", true)).toEqual({ kind: "lite", waitForKokoro: false });
  });

  it("falls back to server speech when the browser has no built-in voice", () => {
    expect(planVoice("lite", "idle", true)).toEqual({ kind: "lite", waitForKokoro: false });
    expect(planVoice("lite", "idle", false)).toEqual({ kind: "orpheus" });
  });
});

describe("parseVoiceChoice", () => {
  it("restores a saved choice and ignores anything else", () => {
    expect(parseVoiceChoice("kokoro")).toBe("kokoro");
    expect(parseVoiceChoice("lite")).toBe("lite");
    expect(parseVoiceChoice("robot")).toBe("orpheus");
    expect(parseVoiceChoice(null)).toBe("orpheus");
  });
});
