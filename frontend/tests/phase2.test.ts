import { describe, expect, it } from "vitest";

import { formatFormValue } from "@/lib/time";
import { toCalendarDay } from "@/realtime/calendarSource";
import type { ServerEvent } from "@/realtime/events";
import {
  addLocalLine,
  applyServerEvent,
  initialCallData,
  mergeCalendarDay,
  type CallData,
} from "@/store/reducer";
import { FILLER_LINE, NUDGE_LINE, SILENCE_GOODBYE_LINE, precachePieces } from "@/voice/phrases";
import { SentencePlayer, type Clip, type Playback, type Voice } from "@/voice/player";

const DAY = "2026-11-04";
const at = (hhmm: string) => `${DAY}T${hhmm}:00+08:00`;

describe("calendar from the API", () => {
  const response = {
    date: DAY,
    busy: [{ id: "seed-7", doctor_id: "dr-reyes", start: at("09:00"), end: at("09:30") }],
    appointments: [
      {
        id: "a1",
        doctor_id: "dr-santos",
        start: at("10:00"),
        end: at("10:30"),
        state: "confirmed" as const,
        patient_name: "Juan",
        expires_at: null,
      },
    ],
  };

  it("maps API rows to calendar slots", () => {
    const day = toCalendarDay(response);
    expect(day.busy).toEqual([
      { id: "seed-7", doctorId: "dr-reyes", start: at("09:00"), end: at("09:30") },
    ]);
    expect(day.appointments[0]).toMatchObject({ id: "a1", state: "confirmed", patientName: "Juan" });
  });

  it("merges a loaded day without overwriting newer live events", () => {
    const live = applyServerEvent(initialCallData, {
      type: "calendar.slot_cancelled",
      id: "a1",
      ts: 5,
    } as ServerEvent);
    const withLiveCancel: CallData = {
      ...live,
      appointments: {
        a1: { id: "a1", doctorId: "dr-santos", start: at("10:00"), end: at("10:30"), state: "cancelled", updatedAt: 5 },
      },
    };
    const merged = mergeCalendarDay(withLiveCancel, toCalendarDay(response));
    expect(merged.busy[DAY]).toHaveLength(1);
    expect(merged.appointments.a1.state).toBe("cancelled");
  });

  it("lets a moved seeded appointment follow its seed id", () => {
    const loaded = mergeCalendarDay(initialCallData, toCalendarDay(response));
    const moved = applyServerEvent(loaded, {
      type: "calendar.slot_moved",
      appointment_id: "seed-7",
      from_start: at("09:00"),
      to_start: at("14:00"),
      doctor_id: "dr-reyes",
      ts: 9,
    } as ServerEvent);
    expect(moved.busy[DAY]).toEqual([]);
    expect(moved.appointments["seed-7"]).toMatchObject({ start: at("14:00"), state: "confirmed" });
  });
});

describe("local lines and form display", () => {
  it("adds silence nudges to the transcript only", () => {
    const s = addLocalLine(initialCallData, NUDGE_LINE, 42);
    expect(s.transcript).toEqual([{ id: "local-42", role: "agent", text: NUDGE_LINE, turnId: null }]);
  });

  it("shows ISO birthdays in words", () => {
    expect(formatFormValue("date_of_birth", "1990-03-03")).toBe("March 3, 1990");
    expect(formatFormValue("date_of_birth", "March 3")).toBe("March 3");
    expect(formatFormValue("phone", "1990-03-03")).toBe("1990-03-03");
  });

  it("pre-generates the filler and silence lines", () => {
    expect(precachePieces()).toEqual(expect.arrayContaining([FILLER_LINE, NUDGE_LINE, SILENCE_GOODBYE_LINE]));
  });
});

/** A voice whose clips finish when the test says so. */
class ManualVoice implements Voice {
  readonly mode = "kokoro";
  playing: { text: string; finish: () => void; stopped: boolean }[] = [];

  async prepare(text: string): Promise<Clip> {
    return {
      play: (): Playback => {
        let finish!: () => void;
        const ended = new Promise<void>((r) => (finish = r));
        const entry = { text, finish, stopped: false };
        this.playing.push(entry);
        return {
          ended,
          stop: () => {
            entry.stopped = true;
            finish();
          },
          progress: () => 0,
        };
      },
    };
  }
}

const tick = () => new Promise((r) => setTimeout(r, 0));

describe("sayAside (filler and nudges)", () => {
  it("plays while a tool runs, and the reply waits for it to finish", async () => {
    const voice = new ManualVoice();
    const player = new SentencePlayer(voice);
    void player.sayAside(FILLER_LINE);
    await tick();
    expect(voice.playing.map((p) => p.text)).toEqual([FILLER_LINE]);
    expect(player.isSpeaking).toBe(true);

    player.enqueue(1, 0, "Sure.");
    await tick();
    expect(voice.playing).toHaveLength(1); // not talking over the filler
    voice.playing[0].finish();
    await tick();
    await tick();
    expect(voice.playing.map((p) => p.text)).toEqual([FILLER_LINE, "Sure."]);
  });

  it("is skipped if Mia is already talking, and cut by a barge-in", async () => {
    const voice = new ManualVoice();
    const player = new SentencePlayer(voice);
    player.enqueue(1, 0, "Hello.");
    await tick();
    expect(await player.sayAside(FILLER_LINE)).toBe(false);

    const idle = new SentencePlayer(new ManualVoice());
    const nudge = idle.sayAside(NUDGE_LINE);
    await tick();
    idle.stop();
    expect(await nudge).toBe(false);
    expect(idle.isSpeaking).toBe(false);
  });
});
