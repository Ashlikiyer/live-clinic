import { describe, expect, it } from "vitest";

import { callClock, deskStatus, type DeskStatusInput } from "@/lib/deskStatus";

const live: DeskStatusInput = { status: "live", agentSpeaking: false, userSpeaking: false, working: false };

describe("deskStatus", () => {
  it("names what is happening, Mia's speech first", () => {
    expect(deskStatus({ ...live, agentSpeaking: true, userSpeaking: true })).toEqual({
      label: "Mia is speaking",
      tone: "speaking",
    });
    expect(deskStatus({ ...live, userSpeaking: true }).label).toBe("You're speaking");
    expect(deskStatus({ ...live, working: true })).toEqual({ label: "Mia is checking", tone: "working" });
    expect(deskStatus(live)).toEqual({ label: "Listening", tone: "listening" });
  });

  it("covers the call's start and end", () => {
    expect(deskStatus({ ...live, status: "connecting" }).label).toBe("Connecting…");
    expect(deskStatus({ ...live, status: "transferring" }).label).toBe("Transferring…");
    expect(deskStatus({ ...live, status: "ended", agentSpeaking: true }).label).toBe("Call ended");
  });
});

describe("callClock", () => {
  it("pads minutes and seconds", () => {
    expect(callClock(0)).toBe("00:00");
    expect(callClock(154.9)).toBe("02:34");
    expect(callClock(3600)).toBe("60:00");
  });
});
