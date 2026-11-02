import { describe, expect, it } from "vitest";

import { slowestStage, turnSegments } from "@/components/xray/segments";
import type { TurnMetric } from "@/store/reducer";

const metric = (overrides: Partial<TurnMetric> = {}): TurnMetric => ({
  turnId: 1,
  stages: {
    vad_wait_ms: 600,
    upload_ms: 100,
    stt_ms: 300,
    llm_ttft_ms: 400,
    first_sentence_ms: 150,
    tts_ms: 250,
  },
  totalMs: 1900,
  interrupted: false,
  toolMs: 0,
  ...overrides,
});

describe("turnSegments", () => {
  it("lists stages in pipeline order and fills the remainder as other", () => {
    const segments = turnSegments(metric());
    expect(segments.map((s) => s.key)).toEqual([
      "vad_wait_ms",
      "upload_ms",
      "stt_ms",
      "llm_ttft_ms",
      "first_sentence_ms",
      "tts_ms",
      "other",
    ]);
    expect(segments.reduce((a, s) => a + s.ms, 0)).toBe(1900);
  });

  it("carves tool time out of the LLM stage as a hatched segment", () => {
    const segments = turnSegments(metric({ toolMs: 150 }));
    expect(segments.find((s) => s.key === "llm_ttft_ms")?.ms).toBe(250);
    expect(segments.find((s) => s.key === "tools")).toMatchObject({ ms: 150, hatched: true });
  });

  it("skips missing stages and never adds negative other time", () => {
    const segments = turnSegments(
      metric({ stages: { ...metric().stages, upload_ms: null }, totalMs: 1000 }),
    );
    expect(segments.some((s) => s.key === "upload_ms" || s.key === "other")).toBe(false);
  });

  it("names the slowest stage", () => {
    expect(slowestStage(metric())?.key).toBe("vad_wait_ms");
  });
});
