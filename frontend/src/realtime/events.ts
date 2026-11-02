/**
 * Typed WebSocket events for /ws/call. Names and payloads follow the spec exactly.
 *
 * Conventions:
 * - `ts` is epoch milliseconds (server or client clock).
 * - `turn_id` is a per-call integer that only increases. The greeting is turn 0.
 * - Calendar times are ISO 8601 strings in clinic local time with offset,
 *   e.g. "2026-11-04T14:30:00+08:00", so `start.slice(0, 10)` is the clinic date.
 */

export type DoctorId = string;

export type VisitType = "general_consult" | "follow_up" | "pediatric_consult" | "annual_checkup";

export type CallOutcome =
  | "booked"
  | "rescheduled"
  | "cancelled"
  | "info_only"
  | "transferred"
  | "emergency_advised"
  | "abandoned";

export type FormField =
  | "full_name"
  | "date_of_birth"
  | "phone"
  | "reason"
  | "symptoms"
  | "symptom_duration"
  | "allergies"
  | "insurance"
  | "preferred_doctor";

export type ToolName =
  | "update_intake_form"
  | "find_patient"
  | "check_availability"
  | "hold_slot"
  | "confirm_booking"
  | "release_hold"
  | "reschedule_appointment"
  | "cancel_appointment"
  | "get_clinic_info"
  | "end_call";

export type ErrorCode =
  | "STT_FAILED"
  | "LLM_FAILED"
  | "TOOL_FAILED"
  | "RATE_LIMITED"
  | "SESSION_EXPIRED"
  | "CALL_LIMIT_REACHED";

export const STAGE_KEYS = [
  "vad_wait_ms",
  "upload_ms",
  "stt_ms",
  "llm_ttft_ms",
  "first_sentence_ms",
  "tts_ms",
] as const;

export type StageKey = (typeof STAGE_KEYS)[number];
export type TurnStages = Record<StageKey, number | null>;

export interface CallStats {
  duration_s: number;
  turn_count: number;
  median_reply_ms: number | null;
  slowest_reply_ms: number | null;
}

type Event<T extends string, P = object> = { type: T; ts: number } & P;

// ---------- Server -> client ----------

export type ServerEvent =
  | Event<"call.ready", { call_id: string; today: string; timezone: string }>
  | Event<"transcript.user.final", { turn_id: number; text: string; stt_ms: number }>
  | Event<"agent.text.delta", { turn_id: number; delta: string }>
  | Event<"agent.sentence", { turn_id: number; index: number; text: string }>
  | Event<"agent.text.done", { turn_id: number }>
  | Event<"tool.started", { turn_id: number; name: ToolName }>
  | Event<"tool.finished", { turn_id: number; name: ToolName; ok: boolean; ms: number }>
  | Event<"form.field_updated", { field: FormField; value: string; corrected: boolean }>
  | Event<"calendar.slots_offered", { date: string; slots: { start: string; doctor_id: DoctorId }[] }>
  | Event<
      "calendar.slot_holding",
      { hold_id: string; start: string; end: string; doctor_id: DoctorId; expires_at: string }
    >
  | Event<
      "calendar.slot_confirmed",
      { appointment_id: string; start: string; end: string; doctor_id: DoctorId; patient_name: string }
    >
  | Event<"calendar.slot_released", { id: string }>
  | Event<"calendar.slot_cancelled", { id: string }>
  | Event<
      "calendar.slot_moved",
      { appointment_id: string; from_start: string; to_start: string; doctor_id: DoctorId }
    >
  | Event<
      "metrics.turn",
      { turn_id: number; stages: TurnStages; total_ms: number; interrupted: boolean }
    >
  | Event<"call.transferring", { reason: string }>
  | Event<"call.ended", { outcome: CallOutcome; summary: string; stats: CallStats }>
  | Event<"error", { code: ErrorCode; message: string; retryable: boolean }>;

export type ServerEventType = ServerEvent["type"];
export type ServerEventOf<T extends ServerEventType> = Extract<ServerEvent, { type: T }>;

// ---------- Client -> server ----------

export type ClientEvent =
  | Event<"call.start", { voice: "kokoro" | "lite"; captions: boolean }>
  | Event<"text.message", { text: string }>
  | Event<"user.interrupt", { turn_id: number; played_text: string; played_ms: number }>
  | Event<"tts.first_audio", { turn_id: number }>
  | Event<"call.end", { reason: "user" }>
  | Event<"ping">;

/** JSON header of a binary audio frame: 4-byte header length + this JSON + WAV bytes. */
export interface AudioUtteranceHeader {
  type: "audio.utterance";
  turn_id: number;
  speech_end_ts: number;
}
