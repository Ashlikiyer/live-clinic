import { describe, expect, it, vi } from "vitest";

import type { ServerEvent } from "@/realtime/events";
import { CallSocket, type SocketStatus } from "@/realtime/socket";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  readyState = 0;
  binaryType = "blob";
  sent: (string | ArrayBuffer)[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((m: { data: unknown }) => void) | null = null;

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string | ArrayBuffer) {
    this.sent.push(data);
  }
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  drop() {
    this.readyState = 3;
    this.onclose?.();
  }
  receive(event: object) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }
}

function setup() {
  FakeWebSocket.instances = [];
  const events: ServerEvent[] = [];
  const statuses: SocketStatus[] = [];
  const onReconnected = vi.fn();
  const socket = new CallSocket({
    url: "ws://test/ws/call?token=t",
    onEvent: (e) => events.push(e),
    onStatus: (s) => statuses.push(s),
    onReconnected,
    WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    reconnectDelayMs: 0,
    pingMs: 15_000,
  });
  return { socket, events, statuses, onReconnected, ws: () => FakeWebSocket.instances.at(-1)! };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("CallSocket", () => {
  it("sends typed JSON events with a timestamp and parses server events", async () => {
    const { socket, events, ws } = setup();
    const connected = socket.connect();
    ws().open();
    await connected;
    socket.send({ type: "text.message", text: "hi" });
    const sent = JSON.parse(ws().sent[0] as string);
    expect(sent).toMatchObject({ type: "text.message", text: "hi" });
    expect(typeof sent.ts).toBe("number");

    ws().receive({ type: "agent.text.done", ts: 1, turn_id: 0 });
    ws().onmessage?.({ data: "not json" });
    expect(events).toEqual([{ type: "agent.text.done", ts: 1, turn_id: 0 }]);
  });

  it("sends audio as a binary frame", async () => {
    const { socket, ws } = setup();
    const connected = socket.connect();
    ws().open();
    await connected;
    socket.sendAudio(
      { type: "audio.utterance", turn_id: 1, speech_end_ts: 5 },
      new Uint8Array([1, 2]).buffer,
    );
    expect(ws().sent[0]).toBeInstanceOf(ArrayBuffer);
  });

  it("pings every 15 seconds", async () => {
    vi.useFakeTimers();
    const { socket, ws } = setup();
    const connected = socket.connect();
    ws().open();
    await connected;
    vi.advanceTimersByTime(30_000);
    const types = ws().sent.map((s) => JSON.parse(s as string).type);
    expect(types).toEqual(["ping", "ping"]);
    socket.close();
    vi.useRealTimers();
  });

  it("reconnects once after an unexpected drop, then gives up", async () => {
    const { socket, statuses, onReconnected, ws } = setup();
    const connected = socket.connect();
    ws().open();
    await connected;

    ws().drop();
    await flush();
    expect(FakeWebSocket.instances).toHaveLength(2);
    ws().open();
    await flush();
    expect(onReconnected).toHaveBeenCalledOnce();

    ws().drop();
    await flush();
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(statuses.at(-1)).toBe("lost");
  });

  it("does not reconnect after close()", async () => {
    const { socket, ws } = setup();
    const connected = socket.connect();
    ws().open();
    await connected;
    socket.close();
    await flush();
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("rejects connect() if the socket never opens", async () => {
    const { socket, ws } = setup();
    const connected = socket.connect();
    ws().drop();
    await expect(connected).rejects.toThrow(/Could not connect/);
  });
});
