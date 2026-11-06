import { describe, expect, it } from "vitest";

import type { ServerEvent } from "@/realtime/events";
import {
  applyServerEvent,
  initialCallData,
  latestConfirmed,
  markInterrupted,
  missingRequiredFields,
  slotKey,
  type CallData,
} from "@/store/reducer";

type WithoutTs<T> = T extends unknown ? Omit<T, "ts"> : never;

function run(events: WithoutTs<ServerEvent>[], state: CallData = initialCallData): CallData {
  return events.reduce<CallData>(
    (s, e, i) => applyServerEvent(s, { ...e, ts: 1000 + i } as ServerEvent),
    state,
  );
}

const DAY = "2026-11-04";
const HOLD = {
  type: "calendar.slot_holding",
  hold_id: "h1",
  start: `${DAY}T14:00:00+08:00`,
  end: `${DAY}T14:30:00+08:00`,
  doctor_id: "dr-reyes",
  expires_at: `${DAY}T14:05:00+08:00`,
} as const;

describe("call lifecycle", () => {
  it("goes live on call.ready and shows today's calendar", () => {
    const s = run([
      { type: "call.ready", call_id: "c1", today: "2026-11-02", timezone: "Asia/Manila" },
    ]);
    expect(s.status).toBe("live");
    expect(s.calendarDate).toBe("2026-11-02");
  });

  it("ends with outcome and adds a transfer notice first", () => {
    const s = run([
      { type: "call.transferring", reason: "caller asked for a person" },
      {
        type: "call.ended",
        outcome: "transferred",
        summary: "Transferred.",
        stats: { duration_s: 30, turn_count: 2, median_reply_ms: 1200, slowest_reply_ms: 1500 },
      },
    ]);
    expect(s.status).toBe("ended");
    expect(s.ended?.outcome).toBe("transferred");
    expect(s.transcript.at(-1)?.text).toMatch(/Transferring/);
  });
});

describe("transcript", () => {
  it("builds agent bubbles from deltas and user bubbles from finals", () => {
    const s = run([
      { type: "agent.text.delta", turn_id: 0, delta: "Hi," },
      { type: "agent.text.delta", turn_id: 0, delta: " how can I help?" },
      { type: "transcript.user.final", turn_id: 1, text: "I need a doctor.", stt_ms: 250 },
    ]);
    expect(s.transcript.map((e) => [e.role, e.text])).toEqual([
      ["agent", "Hi, how can I help?"],
      ["user", "I need a doctor."],
    ]);
  });

  it("drops late agent text for a turn older than the current one", () => {
    const s = run([
      { type: "transcript.user.final", turn_id: 3, text: "Afternoon please", stt_ms: 200 },
      { type: "agent.text.delta", turn_id: 2, delta: "late words" },
    ]);
    expect(s.transcript.some((e) => e.text.includes("late"))).toBe(false);
  });

  it("keeps only the played text after an interruption", () => {
    const spoken = run([
      {
        type: "agent.text.delta",
        turn_id: 2,
        delta: "I'm holding Wednesday at 9:30 AM with Dr. Reyes.",
      },
    ]);
    const s = markInterrupted(spoken, 2, "I'm holding Wednesday ");
    const agent = s.transcript.find((e) => e.id === "agent-2");
    expect(agent?.text).toBe("I'm holding Wednesday");
    expect(agent?.interrupted).toBe(true);
    expect(agent?.unspoken).toBe("at 9:30 AM with Dr. Reyes.");
    expect(s.currentTurnId).toBe(3);
    // Anything still streaming for turn 2 is ignored.
    const after = run([{ type: "agent.text.delta", turn_id: 2, delta: " more" }], s);
    expect(after.transcript.find((e) => e.id === "agent-2")?.text).toBe("I'm holding Wednesday");
  });
});

describe("intake form", () => {
  it("fills fields, marks corrections and tracks required ones", () => {
    const s = run([
      { type: "form.field_updated", field: "full_name", value: "Juan Dela Cruz", corrected: false },
      { type: "form.field_updated", field: "date_of_birth", value: "May 3, 1990", corrected: false },
      { type: "form.field_updated", field: "date_of_birth", value: "March 3, 1990", corrected: true },
    ]);
    expect(s.form.date_of_birth).toMatchObject({ value: "March 3, 1990", corrected: true });
    expect(s.unseen.form).toBe(true);
    expect(missingRequiredFields(s.form)).toEqual(["phone", "reason"]);
  });
});

describe("calendar", () => {
  it("jumps to the offered day and highlights offered slots", () => {
    const s = run([
      {
        type: "calendar.slots_offered",
        date: DAY,
        slots: [{ start: HOLD.start, doctor_id: "dr-reyes" }],
      },
    ]);
    expect(s.calendarDate).toBe(DAY);
    expect(s.offered?.keys).toEqual([slotKey("dr-reyes", HOLD.start)]);
  });

  it("turns a hold into a confirmed appointment", () => {
    const s = run([
      HOLD,
      {
        type: "calendar.slot_confirmed",
        appointment_id: "a1",
        start: HOLD.start,
        end: HOLD.end,
        doctor_id: "dr-reyes",
        patient_name: "Juan Dela Cruz",
      },
    ]);
    expect(Object.keys(s.appointments)).toEqual(["a1"]);
    expect(s.appointments.a1).toMatchObject({ state: "confirmed", patientName: "Juan Dela Cruz" });
    expect(latestConfirmed(s.appointments)?.id).toBe("a1");
  });

  it("removes released holds", () => {
    const s = run([HOLD, { type: "calendar.slot_released", id: "h1" }]);
    expect(s.appointments).toEqual({});
  });

  it("marks cancelled appointments, including seeded ones", () => {
    const seeded: CallData = {
      ...initialCallData,
      busy: {
        [DAY]: [
          {
            id: "seed-9",
            doctorId: "dr-santos",
            start: `${DAY}T10:00:00+08:00`,
            end: `${DAY}T10:30:00+08:00`,
          },
        ],
      },
    };
    const s = run([{ type: "calendar.slot_cancelled", id: "seed-9" }], seeded);
    expect(s.busy[DAY]).toEqual([]);
    expect(s.appointments["seed-9"].state).toBe("cancelled");
  });

  it("moves an appointment and keeps its length", () => {
    const s = run([
      { ...HOLD, hold_id: "a1", end: `${DAY}T15:00:00+08:00` },
      {
        type: "calendar.slot_moved",
        appointment_id: "a1",
        from_start: HOLD.start,
        to_start: `${DAY}T15:30:00+08:00`,
        doctor_id: "dr-reyes",
      },
    ]);
    expect(s.appointments.a1).toMatchObject({
      start: `${DAY}T15:30:00+08:00`,
      end: `${DAY}T16:30:00+08:00`,
      movedFromStart: HOLD.start,
    });
  });

  it("ignores events for unknown appointments", () => {
    const s = run([{ type: "calendar.slot_cancelled", id: "nope" }]);
    expect(s).toEqual(initialCallData);
  });
});

describe("metrics", () => {
  it("records turn metrics with tool time, in turn order", () => {
    const stages = {
      vad_wait_ms: 600,
      upload_ms: 80,
      stt_ms: 300,
      llm_ttft_ms: 250,
      first_sentence_ms: 150,
      tts_ms: 200,
    };
    const s = run([
      { type: "tool.started", turn_id: 2, name: "check_availability" },
      { type: "tool.finished", turn_id: 2, name: "check_availability", ok: true, ms: 120 },
      { type: "metrics.turn", turn_id: 2, stages, total_ms: 1650, interrupted: false },
      { type: "metrics.turn", turn_id: 1, stages, total_ms: 1500, interrupted: true },
    ]);
    expect(s.activeTools).toEqual([]);
    expect(s.metrics.map((m) => [m.turnId, m.toolMs])).toEqual([
      [1, 0],
      [2, 120],
    ]);
  });
});
