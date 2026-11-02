import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { GREETING_SENTENCES, RECOVERY_SENTENCES, phraseKey, precachePieces } from "@/voice/phrases";
import { speechChunks } from "@/voice/turnTaking";

/** Read a Python string constant (possibly built from adjacent literals) from prompt.py. */
function pythonConstant(name: string): string {
  // Normalize CRLF: Windows checkouts (core.autocrlf) have them.
  const source = readFileSync("../backend/app/agent/prompt.py", "utf8").replace(/\r\n/g, "\n");
  // Either `NAME = "..."` on one line, or `NAME = (` + adjacent literals + `)`.
  const match =
    source.match(new RegExp(`^${name} = \\(\\n([\\s\\S]*?)\\n\\)`, "m")) ??
    source.match(new RegExp(`^${name} = (".*")$`, "m"));
  if (!match) throw new Error(`${name} not found in prompt.py`);
  return [...match[1].matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((m) => m[1]).join("");
}

describe("pre-generated phrases", () => {
  it("match the backend's fixed lines word for word", () => {
    expect(GREETING_SENTENCES.join(" ")).toBe(pythonConstant("GREETING"));
    expect(RECOVERY_SENTENCES.slice(0, 2).join(" ")).toBe(pythonConstant("STT_RECOVERY_LINE"));
    expect(RECOVERY_SENTENCES.slice(2, 4).join(" ")).toBe(pythonConstant("LLM_RECOVERY_LINE"));
    expect(RECOVERY_SENTENCES.slice(4, 6).join(" ")).toBe(pythonConstant("RECONNECT_LINE"));
  });

  it("are cached as the exact pieces the player asks for", () => {
    const pieces = precachePieces();
    expect(pieces).toContain("Hi,");
    expect(pieces).toContain("thanks for calling Bayview Family Clinic.");
    expect(pieces).toContain("This is Mia.");
  });
});

describe("phraseKey", () => {
  it("treats punctuation and case variants of an opener as the same clip", () => {
    expect(phraseKey("Sure!")).toBe(phraseKey("sure."));
    expect(phraseKey("Of course.")).toBe("of course");
    expect(phraseKey("Sure.")).not.toBe(phraseKey("Sure, I can help."));
  });

  it("puts the greeting first so it is ready before the first call", () => {
    expect(precachePieces().slice(0, 2)).toEqual(["Hi,", "thanks for calling Bayview Family Clinic."]);
  });
});

describe("speechChunks", () => {
  it("splits only the first sentence, at its first comma", () => {
    expect(speechChunks("Sure, I can help with that.", true)).toEqual(["Sure,", "I can help with that."]);
    expect(speechChunks("Sure, I can help with that.", false)).toEqual(["Sure, I can help with that."]);
  });

  it("leaves sentences alone when splitting wouldn't help", () => {
    expect(speechChunks("Of course.", true)).toEqual(["Of course."]);
    expect(speechChunks("Okay, thanks.", true)).toEqual(["Okay, thanks."]);
    const longLead = "On Tuesday the fourth of November in the afternoon, we have a slot open.";
    expect(speechChunks(longLead, true)).toEqual([longLead]);
  });
});
