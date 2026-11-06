import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { BUSY_NOTICE, isBusyEnding } from "@/lib/busy";

const backend = (path: string) => readFileSync(`../backend/${path}`, "utf8").replace(/\r\n/g, "\n");

describe("busy line", () => {
  it("uses the backend's own busy texts", () => {
    expect(backend("app/call/busy.py")).toContain(`BUSY_NOTICE = "${BUSY_NOTICE}"`);
    const summary = backend("app/agent/prompt.py").match(/^BUSY_SUMMARY = "(.*)"$/m)?.[1] ?? "";
    expect(isBusyEnding("abandoned", summary)).toBe(true);
  });

  it("recognises a busy ending, and only that", () => {
    expect(isBusyEnding("abandoned", BUSY_NOTICE)).toBe(true);
    expect(isBusyEnding("abandoned", "The caller ended the call.")).toBe(false);
    expect(isBusyEnding("booked", BUSY_NOTICE)).toBe(false);
  });
});
