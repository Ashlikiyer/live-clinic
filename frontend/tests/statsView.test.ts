import { describe, expect, it } from "vitest";

import { rankedCauses, rebin, secondsTick, stageBreakdown } from "@/lib/statsView";

describe("stats view helpers", () => {
  it("re-bins 50 ms buckets into continuous display bins", () => {
    const bins = rebin({ "1500": 2, "1550": 1, "1000": 1, "2600": 1 }, 250);
    expect(bins).toHaveLength(11); // 0 .. 2500-2750
    expect(bins[4]).toEqual({ startMs: 1000, endMs: 1250, count: 1 });
    expect(bins[6]).toEqual({ startMs: 1500, endMs: 1750, count: 3 });
    expect(bins[10].count).toBe(1);
    expect(bins.reduce((a, b) => a + b.count, 0)).toBe(5);
    expect(rebin({}, 250)).toEqual([]);
    // Capped: the 11.5 s outlier joins the open "6 s+" bin instead of stretching the axis.
    const capped = rebin({ "1500": 2, "11500": 1 }, 250, 6000);
    expect(capped).toHaveLength(25);
    expect(capped.at(-1)).toEqual({ startMs: 6000, endMs: 6250, count: 1, open: true });
  });

  it("breaks a typical reply into stage shares, skipping unmeasured stages", () => {
    const parts = stageBreakdown({
      vad_wait_ms: 600,
      upload_ms: null,
      stt_ms: 600,
      llm_ttft_ms: 300,
      first_sentence_ms: 0,
      tts_ms: 0,
    });
    expect(parts.map((p) => p.key)).toEqual(["vad_wait_ms", "stt_ms", "llm_ttft_ms"]);
    expect(parts.reduce((a, p) => a + p.share, 0)).toBeCloseTo(1);
    expect(parts[0].share).toBeCloseTo(0.4);
  });

  it("ranks slow-reply causes and formats ticks", () => {
    expect(rankedCauses({ stt_ms: 1, tts_ms: 3, upload_ms: 0 })).toEqual([
      { key: "tts_ms", count: 3 },
      { key: "stt_ms", count: 1 },
    ]);
    expect(secondsTick(2000)).toBe("2 s");
    expect(secondsTick(1250)).toBe("1.3 s");
  });
});
