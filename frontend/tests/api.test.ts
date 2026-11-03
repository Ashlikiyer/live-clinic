import { afterEach, describe, expect, it, vi } from "vitest";

import { API_URL, fetchTranscript } from "@/lib/api";

afterEach(() => vi.unstubAllGlobals());

describe("fetchTranscript", () => {
  it("gets a session, then the stored transcript with a bearer token", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url.endsWith("/api/sessions")) {
        return new Response(
          JSON.stringify({ session_token: "tok", expires_at: "2099-01-01T00:00:00Z" }),
          { status: 201 },
        );
      }
      return new Response("Caller: Hi\nMia: Hello\n", { status: 200 });
    });

    const text = await fetchTranscript("call/1");

    expect(text).toBe("Caller: Hi\nMia: Hello\n");
    expect(calls.at(-1)?.url).toBe(`${API_URL}/api/calls/call%2F1/transcript.txt`);
    expect(new Headers(calls.at(-1)?.init?.headers).get("Authorization")).toBe("Bearer tok");
  });

  it("fails cleanly so the card can fall back to the on-screen transcript", async () => {
    vi.stubGlobal("fetch", async (url: string) =>
      url.endsWith("/api/sessions")
        ? new Response(JSON.stringify({ session_token: "t", expires_at: "2099-01-01T00:00:00Z" }), { status: 201 })
        : new Response("{}", { status: 404 }),
    );
    await expect(fetchTranscript("nope")).rejects.toThrow("Transcript unavailable.");
  });
});
