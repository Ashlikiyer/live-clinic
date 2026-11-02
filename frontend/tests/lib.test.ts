import { describe, expect, it } from "vitest";

import { callStats, median, percentile } from "@/lib/stats";
import {
  addDays,
  addMinutes,
  at,
  clinicDate,
  formatDuration,
  formatMs,
  formatTime,
  minutesOf,
  weekStart,
  weekday,
} from "@/lib/time";
import { transcriptText } from "@/lib/transcript";
import type { TurnMetric } from "@/store/reducer";

describe("time helpers", () => {
  it("uses clinic time for today's date", () => {
    // 2026-11-02 17:30 UTC is already 01:30 on Nov 3 in Manila.
    expect(clinicDate(new Date("2026-11-02T17:30:00Z"))).toBe("2026-11-03");
  });

  it("does date math on YYYY-MM-DD strings", () => {
    expect(addDays("2026-11-30", 1)).toBe("2026-12-01");
    expect(weekday("2026-11-08")).toBe(0);
    expect(weekStart("2026-11-08")).toBe("2026-11-02");
    expect(weekStart("2026-11-04")).toBe("2026-11-02");
  });

  it("builds and reads clinic-local timestamps", () => {
    const iso = at("2026-11-04", "14:30");
    expect(iso).toBe("2026-11-04T14:30:00+08:00");
    expect(minutesOf(iso)).toBe(870);
    expect(addMinutes(iso, 60)).toBe("2026-11-04T15:30:00+08:00");
    expect(formatTime(iso)).toBe("2:30 PM");
  });

  it("formats durations", () => {
    expect(formatDuration(65.9)).toBe("1:05");
    expect(formatMs(850)).toBe("850 ms");
    expect(formatMs(1234)).toBe("1.2 s");
  });
});

describe("stats", () => {
  it("computes median and p95", () => {
    expect(median([])).toBeNull();
    expect(median([3, 1, 2])).toBe(2);
    expect(percentile([1000, 1200, 1400, 1600, 3000], 95)).toBe(2720);
  });

  it("summarises a call", () => {
    const m = (totalMs: number): TurnMetric => ({
      turnId: totalMs,
      totalMs,
      interrupted: false,
      toolMs: 0,
      stages: {
        vad_wait_ms: null,
        upload_ms: null,
        stt_ms: null,
        llm_ttft_ms: null,
        first_sentence_ms: null,
        tts_ms: null,
      },
    });
    expect(callStats([m(1200), m(1800), m(1500)], 95.4)).toEqual({
      duration_s: 95,
      turn_count: 3,
      median_reply_ms: 1500,
      slowest_reply_ms: 1800,
    });
  });
});

describe("transcriptText", () => {
  it("labels speakers and interruptions", () => {
    const text = transcriptText([
      { id: "a", role: "agent", text: "Hello", turnId: 0 },
      { id: "u", role: "user", text: "Hi", turnId: 1 },
      { id: "b", role: "agent", text: "I'm holding", turnId: 1, interrupted: true },
    ]);
    expect(text).toContain("Mia: Hello\nCaller: Hi\nMia: I'm holding [interrupted]");
  });
});
