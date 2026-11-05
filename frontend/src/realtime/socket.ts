/**
 * WebSocket client for one call: typed events, binary audio frames, a 15 s keep-alive ping,
 * and one automatic reconnect within 5 s if the connection drops unexpectedly.
 */

import type { AudioUtteranceHeader, ClientEvent, ServerEvent, TtsAudioHeader } from "./events";
import { buildAudioFrame, parseAudioFrame } from "@/voice/wav";

type WithoutTs<T> = T extends unknown ? Omit<T, "ts"> : never;
export type OutgoingEvent = WithoutTs<ClientEvent>;

export type SocketStatus = "connecting" | "open" | "reconnecting" | "closed" | "lost";

export interface SocketOptions {
  url: string;
  onEvent: (event: ServerEvent) => void;
  /** Binary `tts.audio` frames (server speech). */
  onSpeechAudio?: (header: TtsAudioHeader, pcm: ArrayBuffer) => void;
  onStatus?: (status: SocketStatus) => void;
  /** Called after a successful reconnect, so the caller can resume the call. */
  onReconnected?: () => void;
  WebSocketImpl?: typeof WebSocket;
  pingMs?: number;
  reconnectDelayMs?: number;
}

export class CallSocket {
  private ws: WebSocket | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private closedByUs = false;
  private reconnectUsed = false;

  constructor(private readonly options: SocketOptions) {}

  connect(): Promise<void> {
    return this.open();
  }

  send(event: OutgoingEvent): void {
    if (this.ws?.readyState === 1) this.ws.send(JSON.stringify({ ...event, ts: Date.now() }));
  }

  sendAudio(header: AudioUtteranceHeader, wav: ArrayBuffer): void {
    if (this.ws?.readyState === 1) this.ws.send(buildAudioFrame(header, wav));
  }

  /** Close for good (call ended or user hung up). No reconnect after this. */
  close(): void {
    this.closedByUs = true;
    this.stopPing();
    this.ws?.close();
    this.ws = null;
    this.options.onStatus?.("closed");
  }

  private open(): Promise<void> {
    const Impl = this.options.WebSocketImpl ?? WebSocket;
    this.options.onStatus?.(this.reconnectUsed ? "reconnecting" : "connecting");
    return new Promise<void>((resolve, reject) => {
      const ws = new Impl(this.options.url);
      ws.binaryType = "arraybuffer";
      this.ws = ws;
      let opened = false;

      ws.onopen = () => {
        opened = true;
        this.options.onStatus?.("open");
        this.startPing();
        resolve();
      };
      ws.onmessage = (message: MessageEvent) => {
        if (message.data instanceof ArrayBuffer) {
          const frame = parseAudioFrame(message.data);
          const header = frame?.header as Partial<TtsAudioHeader> | undefined;
          if (frame && header?.type === "tts.audio" && typeof header.id === "number") {
            this.options.onSpeechAudio?.(header as TtsAudioHeader, frame.payload);
          }
          return;
        }
        if (typeof message.data !== "string") return;
        try {
          const event = JSON.parse(message.data) as ServerEvent;
          if (typeof event?.type === "string") this.options.onEvent(event);
        } catch {
          // Ignore malformed frames.
        }
      };
      ws.onclose = () => {
        this.stopPing();
        if (ws !== this.ws) return;
        if (!opened) {
          reject(new Error("Could not connect to the clinic."));
          return;
        }
        if (!this.closedByUs) void this.tryReconnect();
      };
    });
  }

  private async tryReconnect(): Promise<void> {
    if (this.reconnectUsed) {
      this.options.onStatus?.("lost");
      return;
    }
    this.reconnectUsed = true;
    this.options.onStatus?.("reconnecting");
    await new Promise((r) => setTimeout(r, this.options.reconnectDelayMs ?? 500));
    if (this.closedByUs) return;
    try {
      await this.open();
      this.options.onReconnected?.();
    } catch {
      this.options.onStatus?.("lost");
    }
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = setInterval(() => this.send({ type: "ping" }), this.options.pingMs ?? 15_000);
  }

  private stopPing(): void {
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pingTimer = null;
  }
}
