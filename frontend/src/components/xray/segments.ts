import type { StageKey } from "@/realtime/events";
import type { TurnMetric } from "@/store/reducer";

export type SegmentKey = StageKey | "tools" | "other";

export interface Segment {
  key: SegmentKey;
  label: string;
  ms: number;
  color: string;
  hatched?: boolean;
}

export const SEGMENT_META: Record<SegmentKey, { label: string; color: string }> = {
  vad_wait_ms: { label: "End-of-speech wait", color: "var(--stage-vad)" },
  upload_ms: { label: "Upload", color: "var(--stage-upload)" },
  stt_ms: { label: "Speech-to-text", color: "var(--stage-stt)" },
  llm_ttft_ms: { label: "LLM first token", color: "var(--stage-llm)" },
  tools: { label: "Tools (inside LLM)", color: "var(--stage-llm)" },
  first_sentence_ms: { label: "First sentence", color: "var(--stage-sentence)" },
  tts_ms: { label: "Voice start", color: "var(--stage-tts)" },
  other: { label: "Other", color: "var(--stage-other)" },
};

const ORDER: StageKey[] = [
  "vad_wait_ms",
  "upload_ms",
  "stt_ms",
  "llm_ttft_ms",
  "first_sentence_ms",
  "tts_ms",
];

const seg = (key: SegmentKey, ms: number, hatched?: boolean): Segment => ({
  key,
  ms,
  hatched,
  ...SEGMENT_META[key],
});

/**
 * Stacked-bar segments for one reply. Tool time is carved out of the LLM stage and drawn
 * hatched; whatever the stages don't explain (clock skew, scheduling) becomes grey "other".
 */
export function turnSegments(metric: TurnMetric): Segment[] {
  const segments: Segment[] = [];
  for (const key of ORDER) {
    const ms = Math.max(0, metric.stages[key] ?? 0);
    if (key === "llm_ttft_ms" && metric.toolMs > 0) {
      const tools = Math.min(metric.toolMs, ms);
      if (ms - tools > 0) segments.push(seg(key, ms - tools));
      if (tools > 0) segments.push(seg("tools", tools, true));
    } else if (ms > 0) {
      segments.push(seg(key, ms));
    }
  }
  const explained = segments.reduce((sum, s) => sum + s.ms, 0);
  if (metric.totalMs > explained) segments.push(seg("other", metric.totalMs - explained));
  return segments;
}

/** The longest stage of a reply, used to explain slow turns. */
export function slowestStage(metric: TurnMetric): Segment | null {
  const segments = turnSegments(metric).filter((s) => s.key !== "other");
  return segments.reduce<Segment | null>((max, s) => (max === null || s.ms > max.ms ? s : max), null);
}
