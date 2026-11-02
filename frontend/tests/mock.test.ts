import { describe, expect, it } from "vitest";

import { mockBusySlots } from "@/mock/busy";
import { buildDemoScript, nextOpenDay } from "@/mock/demoCall";
import type { ServerEvent } from "@/realtime/events";
import { applyServerEvent, initialCallData, markInterrupted, type CallData } from "@/store/reducer";

describe("mock schedule", () => {
  it("is deterministic, empty on Sundays and keeps requested slots free", () => {
    const day = "2026-11-04";
    const slots = mockBusySlots(day);
    expect(mockBusySlots(day)).toEqual(slots);
    expect(mockBusySlots("2026-11-08")).toEqual([]);
    const key = `${slots[0].doctorId}|${slots[0].start}`;
    expect(mockBusySlots(day, new Set([key])).some((s) => s.id === slots[0].id)).toBe(false);
  });
});

describe("demo script", () => {
  it("skips Sunday when picking the demo day", () => {
    expect(nextOpenDay("2026-11-07")).toBe("2026-11-09");
  });

  it("plays through to a confirmed booking with a corrected birthday", () => {
    const script = buildDemoScript("2026-11-02");
    const times = script.steps.map((s) => s.at);
    expect(times).toEqual([...times].sort((a, b) => a - b));

    let state: CallData = initialCallData;
    for (const step of script.steps) {
      if (step.kind === "event") {
        state = applyServerEvent(state, { ...step.event, ts: step.at } as ServerEvent);
      } else if (step.kind === "interrupt") {
        state = markInterrupted(state, step.turnId, step.playedText);
      }
    }

    expect(state.status).toBe("ended");
    expect(state.ended?.outcome).toBe("booked");
    const confirmed = Object.values(state.appointments).filter((a) => a.state === "confirmed");
    expect(confirmed).toHaveLength(1);
    expect(confirmed[0].start).toBe(`${script.demoDate}T14:00:00+08:00`);
    expect(state.form.date_of_birth?.corrected).toBe(true);
    expect(state.metrics.some((m) => m.interrupted)).toBe(true);
    expect(state.transcript.some((e) => e.interrupted)).toBe(true);
  });
});
