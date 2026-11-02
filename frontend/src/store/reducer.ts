/**
 * Pure state transitions for a call. The UI changes only in response to server events
 * (plus a few explicit client actions), never by guessing. No I/O here: fully unit-tested.
 */

import { addMinutes, dateOf, minutesOf } from "@/lib/time";
import type {
  CallOutcome,
  CallStats,
  DoctorId,
  ErrorCode,
  FormField,
  ServerEvent,
  ToolName,
  TurnStages,
} from "@/realtime/events";

export type CallStatus = "idle" | "connecting" | "live" | "transferring" | "ended";

export interface TranscriptEntry {
  id: string;
  role: "user" | "agent" | "system";
  text: string;
  turnId: number | null;
  interrupted?: boolean;
}

/** A slot already taken in the shared seeded schedule. */
export interface BusySlot {
  id: string;
  doctorId: DoctorId;
  start: string;
  end: string;
}

export type AppointmentState = "holding" | "confirmed" | "cancelled";

/** A slot this session's agent has acted on, drawn on top of the seeded schedule. */
export interface SandboxSlot {
  id: string;
  doctorId: DoctorId;
  start: string;
  end: string;
  state: AppointmentState;
  patientName?: string;
  expiresAt?: string;
  movedFromStart?: string;
  updatedAt: number;
}

export interface FormValue {
  value: string;
  corrected: boolean;
  updatedAt: number;
}

export interface TurnMetric {
  turnId: number;
  stages: TurnStages;
  totalMs: number;
  interrupted: boolean;
  toolMs: number;
}

export interface CallEnded {
  outcome: CallOutcome;
  summary: string;
  stats: CallStats;
}

export interface CallData {
  status: CallStatus;
  callId: string | null;
  today: string | null;
  /** Newest turn started. Agent text for older turns is dropped (late audio after barge-in). */
  currentTurnId: number;
  transcript: TranscriptEntry[];
  calendarDate: string | null;
  /** Seeded busy slots keyed by date. */
  busy: Record<string, BusySlot[]>;
  appointments: Record<string, SandboxSlot>;
  offered: { date: string; keys: string[]; at: number } | null;
  form: Partial<Record<FormField, FormValue>>;
  metrics: TurnMetric[];
  toolMs: Record<number, number>;
  activeTools: ToolName[];
  unseen: { calendar: boolean; form: boolean };
  ended: CallEnded | null;
  transferReason: string | null;
  lastError: { code: ErrorCode; message: string } | null;
}

export const initialCallData: CallData = {
  status: "idle",
  callId: null,
  today: null,
  currentTurnId: 0,
  transcript: [],
  calendarDate: null,
  busy: {},
  appointments: {},
  offered: null,
  form: {},
  metrics: [],
  toolMs: {},
  activeTools: [],
  unseen: { calendar: false, form: false },
  ended: null,
  transferReason: null,
  lastError: null,
};

export function slotKey(doctorId: DoctorId, start: string): string {
  return `${doctorId}|${start}`;
}

const AGENT_TEXT_EVENTS = new Set(["agent.text.delta", "agent.sentence", "agent.text.done"]);

function isStale(state: CallData, event: ServerEvent): boolean {
  return (
    AGENT_TEXT_EVENTS.has(event.type) &&
    "turn_id" in event &&
    event.turn_id < state.currentTurnId
  );
}

function touchCalendar(state: CallData, date: string): CallData {
  return { ...state, calendarDate: date, unseen: { ...state.unseen, calendar: true } };
}

function upsertMetric(metrics: TurnMetric[], metric: TurnMetric): TurnMetric[] {
  const rest = metrics.filter((m) => m.turnId !== metric.turnId);
  return [...rest, metric].sort((a, b) => a.turnId - b.turnId);
}

function findBusy(state: CallData, id: string): BusySlot | undefined {
  for (const slots of Object.values(state.busy)) {
    const hit = slots.find((s) => s.id === id);
    if (hit) return hit;
  }
  return undefined;
}

function withoutBusy(state: CallData, slot: BusySlot): Record<string, BusySlot[]> {
  const date = dateOf(slot.start);
  return { ...state.busy, [date]: (state.busy[date] ?? []).filter((s) => s.id !== slot.id) };
}

export function applyServerEvent(state: CallData, event: ServerEvent): CallData {
  if (isStale(state, event)) return state;

  switch (event.type) {
    case "call.ready":
      return {
        ...state,
        status: "live",
        callId: event.call_id,
        today: event.today,
        calendarDate: state.calendarDate ?? event.today,
      };

    case "transcript.user.final":
      return {
        ...state,
        currentTurnId: Math.max(state.currentTurnId, event.turn_id),
        transcript: [
          ...state.transcript.filter((e) => e.id !== `user-${event.turn_id}`),
          { id: `user-${event.turn_id}`, role: "user", text: event.text, turnId: event.turn_id },
        ],
      };

    case "agent.text.delta": {
      const id = `agent-${event.turn_id}`;
      const existing = state.transcript.find((e) => e.id === id);
      const transcript = existing
        ? state.transcript.map((e) => (e.id === id ? { ...e, text: e.text + event.delta } : e))
        : [
            ...state.transcript,
            { id, role: "agent" as const, text: event.delta, turnId: event.turn_id },
          ];
      return { ...state, transcript };
    }

    case "agent.sentence":
    case "agent.text.done":
      // Consumed by the voice player; the transcript is built from deltas.
      return state;

    case "tool.started":
      return { ...state, activeTools: [...state.activeTools, event.name] };

    case "tool.finished": {
      const index = state.activeTools.indexOf(event.name);
      const activeTools =
        index === -1 ? state.activeTools : state.activeTools.filter((_, i) => i !== index);
      const toolMs = { ...state.toolMs, [event.turn_id]: (state.toolMs[event.turn_id] ?? 0) + event.ms };
      const metrics = state.metrics.map((m) =>
        m.turnId === event.turn_id ? { ...m, toolMs: toolMs[event.turn_id] } : m,
      );
      return { ...state, activeTools, toolMs, metrics };
    }

    case "form.field_updated":
      return {
        ...state,
        form: {
          ...state.form,
          [event.field]: { value: event.value, corrected: event.corrected, updatedAt: event.ts },
        },
        unseen: { ...state.unseen, form: true },
      };

    case "calendar.slots_offered":
      return {
        ...touchCalendar(state, event.date),
        offered: {
          date: event.date,
          keys: event.slots.map((s) => slotKey(s.doctor_id, s.start)),
          at: event.ts,
        },
      };

    case "calendar.slot_holding":
      return {
        ...touchCalendar(state, dateOf(event.start)),
        appointments: {
          ...state.appointments,
          [event.hold_id]: {
            id: event.hold_id,
            doctorId: event.doctor_id,
            start: event.start,
            end: event.end,
            state: "holding",
            expiresAt: event.expires_at,
            updatedAt: event.ts,
          },
        },
      };

    case "calendar.slot_confirmed": {
      // The hold becomes the appointment: drop holds for the same doctor and start time.
      const appointments = Object.fromEntries(
        Object.entries(state.appointments).filter(
          ([, a]) =>
            !(a.state === "holding" && a.doctorId === event.doctor_id && a.start === event.start),
        ),
      );
      appointments[event.appointment_id] = {
        id: event.appointment_id,
        doctorId: event.doctor_id,
        start: event.start,
        end: event.end,
        state: "confirmed",
        patientName: event.patient_name,
        updatedAt: event.ts,
      };
      return { ...touchCalendar(state, dateOf(event.start)), appointments, offered: null };
    }

    case "calendar.slot_released": {
      const appointments = { ...state.appointments };
      delete appointments[event.id];
      return { ...state, appointments, unseen: { ...state.unseen, calendar: true } };
    }

    case "calendar.slot_cancelled": {
      const existing = state.appointments[event.id];
      if (existing) {
        return {
          ...touchCalendar(state, dateOf(existing.start)),
          appointments: {
            ...state.appointments,
            [event.id]: { ...existing, state: "cancelled", updatedAt: event.ts },
          },
        };
      }
      const seeded = findBusy(state, event.id);
      if (!seeded) return state;
      return {
        ...touchCalendar(state, dateOf(seeded.start)),
        busy: withoutBusy(state, seeded),
        appointments: {
          ...state.appointments,
          [event.id]: { ...seeded, state: "cancelled", updatedAt: event.ts },
        },
      };
    }

    case "calendar.slot_moved": {
      const existing = state.appointments[event.appointment_id];
      const seeded = existing ? undefined : findBusy(state, event.appointment_id);
      const source = existing ?? seeded;
      if (!source) return state;
      const duration = minutesOf(source.end) - minutesOf(source.start);
      const moved: SandboxSlot = {
        id: event.appointment_id,
        doctorId: event.doctor_id,
        start: event.to_start,
        end: addMinutes(event.to_start, duration),
        state: "confirmed",
        patientName: existing?.patientName,
        movedFromStart: event.from_start,
        updatedAt: event.ts,
      };
      return {
        ...touchCalendar(state, dateOf(event.to_start)),
        busy: seeded ? withoutBusy(state, seeded) : state.busy,
        appointments: { ...state.appointments, [event.appointment_id]: moved },
      };
    }

    case "metrics.turn":
      return {
        ...state,
        metrics: upsertMetric(state.metrics, {
          turnId: event.turn_id,
          stages: event.stages,
          totalMs: event.total_ms,
          interrupted: event.interrupted,
          toolMs: state.toolMs[event.turn_id] ?? 0,
        }),
      };

    case "call.transferring":
      return {
        ...state,
        status: "transferring",
        transferReason: event.reason,
        transcript: [
          ...state.transcript,
          {
            id: `system-transfer-${event.ts}`,
            role: "system",
            text: "Transferring to front desk staff...",
            turnId: null,
          },
        ],
      };

    case "call.ended":
      return {
        ...state,
        status: "ended",
        activeTools: [],
        ended: { outcome: event.outcome, summary: event.summary, stats: event.stats },
      };

    case "error":
      return { ...state, lastError: { code: event.code, message: event.message } };
  }
}

/**
 * Barge-in: keep only the words the caller actually heard, so the transcript matches
 * the history the server keeps, and drop any further text for that turn.
 */
export function markInterrupted(state: CallData, turnId: number, playedText: string): CallData {
  const id = `agent-${turnId}`;
  return {
    ...state,
    currentTurnId: Math.max(state.currentTurnId, turnId + 1),
    transcript: state.transcript.map((e) =>
      e.id === id ? { ...e, text: playedText.trim(), interrupted: true } : e,
    ),
  };
}

/** Required before `confirm_booking`, per the spec. */
export const REQUIRED_FIELDS: FormField[] = ["full_name", "date_of_birth", "phone", "reason"];

export function missingRequiredFields(form: CallData["form"]): FormField[] {
  return REQUIRED_FIELDS.filter((f) => !form[f]?.value);
}

/** The appointment to show on the summary card: the latest confirmed one, if any. */
export function latestConfirmed(appointments: CallData["appointments"]): SandboxSlot | null {
  const confirmed = Object.values(appointments).filter((a) => a.state === "confirmed");
  return confirmed.sort((a, b) => b.updatedAt - a.updatedAt)[0] ?? null;
}
