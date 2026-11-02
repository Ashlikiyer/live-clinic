import type { TranscriptEntry } from "@/store/reducer";

import { CLINIC_NAME } from "./clinic";

const SPEAKER: Record<TranscriptEntry["role"], string> = {
  user: "Caller",
  agent: "Mia",
  system: "System",
};

/** Plain-text transcript for the "Download transcript" button. */
export function transcriptText(entries: TranscriptEntry[], header: string[] = []): string {
  const lines = [
    `${CLINIC_NAME} (demo) - call transcript`,
    ...header,
    "",
    ...entries.map((e) => `${SPEAKER[e.role]}: ${e.text}${e.interrupted ? " [interrupted]" : ""}`),
  ];
  return `${lines.join("\n")}\n`;
}
