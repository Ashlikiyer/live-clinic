/**
 * Phase 0: a scripted call that follows the spec's two-minute demo, emitted as the same
 * typed server events the real backend will send. Phase 1 replaces this with the socket.
 */

import { addDays, at, formatLongDate, weekday } from "@/lib/time";
import type { ServerEvent, StageKey, TurnStages } from "@/realtime/events";
import { slotKey } from "@/store/reducer";

type WithoutTs<T> = T extends unknown ? Omit<T, "ts"> : never;
export type DemoEvent = WithoutTs<ServerEvent>;

export type DemoStep =
  | { at: number; kind: "event"; event: DemoEvent }
  | { at: number; kind: "speaking"; speaking: boolean }
  | { at: number; kind: "mic"; level: number }
  | { at: number; kind: "interrupt"; turnId: number; playedText: string };

export interface DemoScript {
  steps: DemoStep[];
  demoDate: string;
  /** Slots the script books, kept free in the mock seeded schedule. */
  freeKeys: string[];
}

const WORD_MS = 240;

class ScriptBuilder {
  steps: DemoStep[] = [];
  t = 0;

  event(event: DemoEvent, gap = 0): this {
    this.t += gap;
    this.steps.push({ at: this.t, kind: "event", event });
    return this;
  }

  wait(ms: number): this {
    this.t += ms;
    return this;
  }

  /** Caller speaks for a while, then the final transcript arrives. */
  user(turnId: number, text: string): this {
    const speakMs = text.split(" ").length * WORD_MS;
    this.steps.push({ at: this.t, kind: "mic", level: 0.7 });
    this.t += speakMs;
    this.steps.push({ at: this.t, kind: "mic", level: 0 });
    this.t += 900;
    return this.event({ type: "transcript.user.final", turn_id: turnId, text, stt_ms: 280 });
  }

  /** Agent streams text word by word and "speaks" it. Stops early if `cutAfterWords`. */
  agent(turnId: number, text: string, cutAfterWords?: number): this {
    const words = text.split(" ");
    const spoken = cutAfterWords ?? words.length;
    this.t += 250;
    this.steps.push({ at: this.t, kind: "speaking", speaking: true });
    words.slice(0, spoken).forEach((word, i) => {
      this.event(
        { type: "agent.text.delta", turn_id: turnId, delta: i === 0 ? word : ` ${word}` },
        i === 0 ? 0 : WORD_MS,
      );
    });
    this.t += WORD_MS;
    if (cutAfterWords !== undefined) {
      this.steps.push({
        at: this.t,
        kind: "interrupt",
        turnId,
        playedText: words.slice(0, spoken).join(" "),
      });
      return this;
    }
    this.steps.push({ at: this.t, kind: "speaking", speaking: false });
    return this.event({ type: "agent.text.done", turn_id: turnId });
  }

  tool(turnId: number, name: Extract<DemoEvent, { type: "tool.started" }>["name"], ms: number, events: DemoEvent[]): this {
    this.event({ type: "tool.started", turn_id: turnId, name }, 150);
    this.t += ms;
    events.forEach((e) => this.event(e));
    return this.event({ type: "tool.finished", turn_id: turnId, name, ok: true, ms });
  }

  metrics(turnId: number, base: number, interrupted = false): this {
    const values: Record<StageKey, number> = {
      vad_wait_ms: 600,
      upload_ms: 70 + (base % 5) * 12,
      stt_ms: 240 + (base % 4) * 35,
      llm_ttft_ms: 190 + (base % 3) * 70,
      first_sentence_ms: 120 + (base % 4) * 40,
      tts_ms: 210 + (base % 5) * 45,
    };
    const stages: TurnStages = values;
    const sum = Object.values(values).reduce((a, b) => a + b, 0);
    return this.event({
      type: "metrics.turn",
      turn_id: turnId,
      stages,
      total_ms: sum + 40 + (base % 3) * 30,
      interrupted,
    });
  }
}

/** First open clinic day after today (Sunday is closed). */
export function nextOpenDay(today: string): string {
  let day = addDays(today, 1);
  while (weekday(day) === 0) day = addDays(day, 1);
  return day;
}

export function buildDemoScript(today: string): DemoScript {
  const day = nextOpenDay(today);
  const spokenDay = formatLongDate(day);
  const am1 = { start: at(day, "09:30"), end: at(day, "10:00"), doctor_id: "dr-reyes" };
  const am2 = { start: at(day, "10:30"), end: at(day, "11:00"), doctor_id: "dr-santos" };
  const pm1 = { start: at(day, "14:00"), end: at(day, "14:30"), doctor_id: "dr-reyes" };
  const pm2 = { start: at(day, "15:30"), end: at(day, "16:00"), doctor_id: "dr-santos" };
  const field = (f: Extract<DemoEvent, { type: "form.field_updated" }>["field"], value: string, corrected = false): DemoEvent => ({
    type: "form.field_updated",
    field: f,
    value,
    corrected,
  });

  const s = new ScriptBuilder();
  s.event({ type: "call.ready", call_id: "demo-call", today, timezone: "Asia/Manila" })
    .agent(0, "Hi, thanks for calling Bayview Family Clinic, a demo clinic. This is Mia. How can I help you today?")
    .wait(600)
    .user(1, "Hi, I'd like to see a doctor this week, I've had a cough for five days.")
    .tool(1, "update_intake_form", 45, [
      field("reason", "Cough"),
      field("symptoms", "Cough"),
      field("symptom_duration", "5 days"),
    ])
    .metrics(1, 1)
    .agent(1, "I'm sorry to hear that. I can book you a visit. May I have your full name?")
    .wait(500)
    .user(2, "It's Juan Dela Cruz.")
    .tool(2, "update_intake_form", 38, [field("full_name", "Juan Dela Cruz")])
    .metrics(2, 2)
    .agent(2, "Thanks, Juan. What's your date of birth?")
    .wait(500)
    .user(3, "May 3, 1990.")
    .tool(3, "update_intake_form", 35, [field("date_of_birth", "May 3, 1990")])
    .metrics(3, 3)
    .agent(3, "Got it. And the best phone number to reach you?")
    .wait(500)
    .user(4, "0917 555 0123. Oh wait, my birthday is actually March 3.")
    .tool(4, "update_intake_form", 41, [
      field("phone", "0917 555 0123"),
      field("date_of_birth", "March 3, 1990", true),
    ])
    .metrics(4, 4)
    .agent(4, "No problem, I've changed it to March 3, 1990. That's 0917, 555, 0123. Which day works for you?")
    .wait(500)
    .user(5, `${spokenDay.split(",")[0]} morning, any doctor is fine.`)
    .tool(5, "check_availability", 120, [
      { type: "calendar.slots_offered", date: day, slots: [am1, am2].map(({ start, doctor_id }) => ({ start, doctor_id })) },
    ])
    .metrics(5, 5)
    .agent(5, `On ${spokenDay}, I have 9:30 AM with Dr. Ana Reyes or 10:30 AM with Dr. Lea Santos. Which do you prefer?`)
    .wait(500)
    .user(6, "9:30 please.")
    .tool(6, "hold_slot", 85, [
      { type: "calendar.slot_holding", hold_id: "hold-1", ...am1, expires_at: at(day, "09:35") },
    ])
    .metrics(6, 6, true)
    .agent(
      6,
      `I'm holding ${spokenDay} at 9:30 AM with Dr. Ana Reyes for a general consult. Shall I confirm it?`,
      7,
    )
    .user(7, "Actually, can we do the afternoon?")
    .tool(7, "release_hold", 30, [{ type: "calendar.slot_released", id: "hold-1" }])
    .tool(7, "check_availability", 110, [
      { type: "calendar.slots_offered", date: day, slots: [pm1, pm2].map(({ start, doctor_id }) => ({ start, doctor_id })) },
    ])
    .metrics(7, 7)
    .agent(7, "Sure. I have 2:00 PM with Dr. Ana Reyes or 3:30 PM with Dr. Lea Santos.")
    .wait(500)
    .user(8, "2 PM works.")
    .tool(8, "hold_slot", 80, [
      { type: "calendar.slot_holding", hold_id: "hold-2", ...pm1, expires_at: at(day, "14:05") },
    ])
    .metrics(8, 8)
    .agent(8, `So that's Dr. Ana Reyes, ${spokenDay}, at 2:00 PM, for a general consult. Shall I confirm?`)
    .wait(400)
    .user(9, "Yes, please.")
    .tool(9, "confirm_booking", 95, [
      { type: "calendar.slot_confirmed", appointment_id: "appt-1", ...pm1, patient_name: "Juan Dela Cruz" },
    ])
    .metrics(9, 9)
    .agent(9, "You're all set. Please arrive 10 minutes early. Is there anything else?")
    .wait(500)
    .user(10, "No, that's all. Thank you!")
    .metrics(10, 10)
    .agent(10, "Take care, Juan. Goodbye!")
    .tool(10, "end_call", 60, [])
    .event(
      {
        type: "call.ended",
        outcome: "booked",
        summary: `Booked a general consult with Dr. Ana Reyes on ${spokenDay} at 2:00 PM for a five-day cough.`,
        stats: { duration_s: 0, turn_count: 10, median_reply_ms: null, slowest_reply_ms: null },
      },
      400,
    );

  return {
    steps: s.steps,
    demoDate: day,
    freeKeys: [am1, am2, pm1, pm2].map((x) => slotKey(x.doctor_id, x.start)),
  };
}
