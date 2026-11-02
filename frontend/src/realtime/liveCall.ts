/**
 * One live call: microphone (VAD) -> socket -> server events -> store + sentence player.
 * Owns barge-in: if the caller talks over Mia for BARGE_IN_MIN_MS, her audio stops and the
 * server is told exactly what was heard.
 */

import { ApiError, callSocketUrl, fetchClinic, forgetSession, getSessionToken } from "@/lib/api";
import { callStats } from "@/lib/stats";
import { useCallStore } from "@/store/callStore";
import { FILLER_LINE, NUDGE_LINE, SILENCE_GOODBYE_LINE } from "@/voice/phrases";
import { SentencePlayer, type Voice } from "@/voice/player";
import { LiteVoice, resumeAudio } from "@/voice/tts";
import { BARGE_IN_MIN_MS, SlowVoiceDetector, shouldSendUtterance, type Utterance } from "@/voice/turnTaking";
import { MicError, startMic, type Mic, type SpeechEndInfo } from "@/voice/vad";
import { encodeWav } from "@/voice/wav";

import { setCalendarSource } from "./calendarSource";
import type { ServerEvent } from "./events";
import { CallSocket } from "./socket";

const END_TIMEOUT_MS = 3000;
/** Play the filler line if a tool runs this long with nothing said yet. */
const FILLER_AFTER_MS = 700;
/** Ask "Are you still there?" after this much silence, then end after the same again. */
const SILENCE_MS = 8000;

const ERROR_NOTICES: Partial<Record<string, string>> = {
  RATE_LIMITED: "Busy right now, try again in a minute.",
  CALL_LIMIT_REACHED: "You've reached today's demo call limit. Please try again tomorrow.",
  SESSION_EXPIRED: "Your demo session expired. Please start a new call.",
};

const store = () => useCallStore.getState();

export class LiveCall {
  private socket: CallSocket | null = null;
  private mic: Mic | null = null;
  private readonly player: SentencePlayer;
  private readonly slowVoice = new SlowVoiceDetector();
  private callId: string | null = null;
  private utterance: Utterance | null = null;
  private bargeTimer: ReturnType<typeof setTimeout> | null = null;
  private finished = false;
  private endWaiter: (() => void) | null = null;
  private fillerTimer: ReturnType<typeof setTimeout> | null = null;
  private silenceTimer: ReturnType<typeof setTimeout> | null = null;
  private nudged = false;

  constructor(private voice: Voice) {
    this.player = new SentencePlayer(voice, {
      onSpeakingChange: (speaking) => {
        store().setAgentSpeaking(speaking);
        if (speaking) this.clearSilence();
        else this.armSilence();
      },
      onFirstAudio: (turnId, ttsMs) => this.onFirstAudio(turnId, ttsMs),
    });
  }

  async start(): Promise<void> {
    store().startCall(Date.now(), "live");
    store().setVoiceMode(this.voice.mode);
    await resumeAudio().catch(() => undefined);

    let token: string;
    try {
      token = await getSessionToken();
    } catch (error) {
      this.failToStart(error instanceof ApiError ? (ERROR_NOTICES[error.code] ?? error.message) : null);
      return;
    }

    // Ask for the mic before connecting, so Mia doesn't greet a permission dialog.
    store().setMic("starting");
    try {
      this.mic = await startMic({
        onSpeechStart: () => this.onSpeechStart(),
        onSpeechEnd: (audio, info) => this.onSpeechEnd(audio, info),
        onMisfire: () => this.onMisfire(),
        onLevel: (level) => {
          if (!store().muted) store().setMicLevel(level);
        },
      });
      store().setMic("listening");
    } catch (error) {
      store().setMic(error instanceof MicError ? error.reason : "unavailable");
    }
    if (this.finished) return;

    // The calendar shows this caller's real sandbox, and doctors come from the clinic API.
    setCalendarSource(token);
    fetchClinic(token)
      .then((clinic) => store().setDoctors(clinic.doctors))
      .catch(() => undefined);

    this.socket = new CallSocket({
      url: callSocketUrl(token),
      onEvent: (event) => this.onEvent(event),
      onStatus: (status) => {
        store().setConnection(status);
        if (status === "lost") this.endLocally("abandoned", "The connection to the clinic was lost.");
      },
      onReconnected: () => this.sendCallStart(this.callId ?? undefined),
    });
    try {
      await this.socket.connect();
    } catch {
      this.failToStart(null);
      return;
    }
    this.sendCallStart();
  }

  sendText(text: string): void {
    const trimmed = text.trim();
    if (!trimmed || this.finished) return;
    if (this.player.isSpeaking) this.bargeIn();
    this.callerActive();
    store().beginTurn(store().currentTurnId + 1);
    this.socket?.send({ type: "text.message", text: trimmed });
  }

  async setMuted(muted: boolean): Promise<void> {
    store().setMuted(muted);
    if (muted) await this.mic?.pause();
    else await this.mic?.resume();
  }

  /** Caller pressed End call: ask the server to wrap up, but don't wait forever. */
  async end(reason: "user" | "silence" = "user"): Promise<void> {
    if (this.finished) return;
    const ended = new Promise<void>((resolve) => (this.endWaiter = resolve));
    this.socket?.send({ type: "call.end", reason });
    await Promise.race([ended, new Promise((r) => setTimeout(r, END_TIMEOUT_MS))]);
    this.endLocally(
      "abandoned",
      reason === "silence" ? "The caller went silent." : "The caller ended the call.",
    );
  }

  /** The caller typed something: silence rules start over. */
  callerActive(): void {
    this.nudged = false;
    this.clearSilence();
  }

  /** Stop everything at once, including audio (leaving the page or starting over). */
  dispose(): void {
    this.player.stop();
    this.teardown();
  }

  // ---------- server events ----------

  private sendCallStart(resumeCallId?: string): void {
    this.socket?.send({
      type: "call.start",
      voice: this.player.voiceMode,
      captions: false,
      ...(resumeCallId ? { resume_call_id: resumeCallId } : {}),
    });
  }

  private onEvent(event: ServerEvent): void {
    if (event.type === "call.ready") this.callId = event.call_id;
    store().applyEvent(event);

    switch (event.type) {
      case "tool.started":
        this.armFiller(event.turn_id);
        break;
      case "agent.sentence":
        this.clearFiller();
        if (event.turn_id >= store().currentTurnId) {
          this.player.enqueue(event.turn_id, event.index, event.text);
        }
        break;
      case "agent.text.done":
        this.clearFiller();
        this.player.markDone(event.turn_id);
        break;
      case "error": {
        const notice = ERROR_NOTICES[event.code];
        if (notice) store().setNotice(notice);
        if (event.code === "SESSION_EXPIRED") forgetSession();
        if (!event.retryable && event.code !== "STT_FAILED" && event.code !== "LLM_FAILED") {
          this.endLocally("abandoned", notice ?? event.message);
        }
        break;
      }
      case "call.ended":
        // Let Mia finish her last sentence; just stop listening and hang up the socket.
        this.endWaiter?.();
        this.teardown();
        break;
    }
  }

  // ---------- microphone ----------

  private onSpeechStart(): void {
    if (this.finished || store().muted) return;
    this.callerActive();
    store().setUserSpeaking(true);
    const agentSpeakingAtStart = this.player.isSpeaking;
    this.utterance = { agentSpeakingAtStart, bargedIn: false };
    if (agentSpeakingAtStart) {
      this.bargeTimer = setTimeout(() => this.bargeIn(), BARGE_IN_MIN_MS);
    }
  }

  private onMisfire(): void {
    this.clearBargeTimer();
    this.utterance = null;
    store().setUserSpeaking(false);
  }

  private onSpeechEnd(audio: Float32Array, info: SpeechEndInfo): void {
    this.clearBargeTimer();
    store().setUserSpeaking(false);
    const utterance = this.utterance ?? { agentSpeakingAtStart: false, bargedIn: false };
    this.utterance = null;
    if (this.finished || store().muted || !shouldSendUtterance(utterance)) return;
    // Mia may have started talking mid-utterance: the caller's words win.
    if (this.player.isSpeaking) this.bargeIn();

    const turnId = store().currentTurnId + 1;
    store().beginTurn(turnId);
    this.socket?.sendAudio(
      {
        type: "audio.utterance",
        turn_id: turnId,
        speech_end_ts: info.speechEndTs,
        vad_wait_ms: info.vadWaitMs,
      },
      encodeWav(audio),
    );
  }

  private bargeIn(): void {
    this.clearBargeTimer();
    if (!this.player.isSpeaking) return;
    if (this.utterance) this.utterance.bargedIn = true;
    const turnId = this.player.activeTurnId;
    const heard = this.player.stop();
    const playedText = heard?.playedText ?? "";
    this.socket?.send({
      type: "user.interrupt",
      turn_id: turnId,
      played_text: playedText,
      played_ms: heard?.playedMs ?? 0,
    });
    store().interrupt(turnId, playedText);
  }

  private clearBargeTimer(): void {
    if (this.bargeTimer) clearTimeout(this.bargeTimer);
    this.bargeTimer = null;
  }

  // ---------- filler and silence ----------

  private armFiller(turnId: number): void {
    if (this.fillerTimer || this.player.isSpeaking) return;
    this.fillerTimer = setTimeout(() => {
      this.fillerTimer = null;
      if (!this.finished && !this.player.isSpeaking && turnId >= store().currentTurnId) {
        void this.player.sayAside(FILLER_LINE);
      }
    }, FILLER_AFTER_MS);
  }

  private clearFiller(): void {
    if (this.fillerTimer) clearTimeout(this.fillerTimer);
    this.fillerTimer = null;
  }

  /** Mia just stopped talking: if the caller says nothing for 8 s, check in. */
  private armSilence(): void {
    this.clearSilence();
    const s = store();
    if (this.finished || s.mic !== "listening" || s.muted || s.status !== "live") return;
    this.silenceTimer = setTimeout(() => void this.onSilence(), SILENCE_MS);
  }

  private clearSilence(): void {
    if (this.silenceTimer) clearTimeout(this.silenceTimer);
    this.silenceTimer = null;
  }

  private async onSilence(): Promise<void> {
    this.silenceTimer = null;
    if (this.finished || store().userSpeaking || this.player.isSpeaking) return;
    if (!this.nudged) {
      this.nudged = true;
      store().addLocalLine(NUDGE_LINE);
      await this.player.sayAside(NUDGE_LINE);
      return; // speaking -> silent re-arms the timer for the second 8 s
    }
    store().addLocalLine(SILENCE_GOODBYE_LINE);
    await this.player.sayAside(SILENCE_GOODBYE_LINE);
    await this.end("silence");
  }

  // ---------- voice ----------

  private onFirstAudio(turnId: number, ttsMs: number): void {
    this.socket?.send({ type: "tts.first_audio", turn_id: turnId, tts_ms: ttsMs });
    if (this.slowVoice.record(ttsMs) && this.voice.mode === "kokoro" && LiteVoice.available()) {
      this.voice = new LiteVoice();
      this.player.setVoice(this.voice);
      store().setVoiceMode("lite");
    }
  }

  // ---------- ending ----------

  private failToStart(notice: string | null): void {
    store().setNotice(notice ?? "Can't reach the clinic right now. Please try again in a minute.");
    this.endLocally("abandoned", "The call could not connect.");
  }

  /** End without the server (connection lost, timeout, startup failure). */
  private endLocally(outcome: "abandoned", summary: string): void {
    const s = store();
    if (s.status !== "ended") {
      const now = Date.now();
      s.applyEvent({
        type: "call.ended",
        ts: now,
        outcome,
        summary,
        stats: callStats(s.metrics, (now - (s.startedAt ?? now)) / 1000),
      });
    }
    this.teardown();
  }

  private teardown(): void {
    this.finished = true;
    this.clearBargeTimer();
    this.clearFiller();
    this.clearSilence();
    void this.mic?.destroy();
    this.mic = null;
    this.socket?.close();
    this.socket = null;
    store().setMicLevel(0);
    store().setUserSpeaking(false);
  }
}
