/**
 * One live call: microphone (VAD) -> socket -> server events -> store + sentence player.
 * Owns barge-in: if the caller talks over Mia for BARGE_IN_MIN_MS, her audio stops and the
 * server is told exactly what was heard.
 */

import { ApiError, callSocketUrl, fetchClinic, forgetSession, getSessionToken } from "@/lib/api";
import { callStats } from "@/lib/stats";
import { useCallStore } from "@/store/callStore";
import { FallbackVoice, OrpheusVoice } from "@/voice/orpheus";
import { FILLER_LINE, NUDGE_LINE, SILENCE_GOODBYE_LINE } from "@/voice/phrases";
import { SentencePlayer, type Voice } from "@/voice/player";
import { LiteVoice, kokoroPreferred, loadKokoro, resumeAudio } from "@/voice/tts";
import {
  BARGE_IN_MIN_MS,
  SlowVoiceDetector,
  shouldSendUtterance,
  shouldSwitchToKokoro,
  type Utterance,
} from "@/voice/turnTaking";
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
  /** performance.now() when the caller's current speech began (for barge-in stop time). */
  private speechStartedAt = 0;
  private bargeTimer: ReturnType<typeof setTimeout> | null = null;
  private finished = false;
  private endWaiter: (() => void) | null = null;
  private fillerTimer: ReturnType<typeof setTimeout> | null = null;
  private silenceTimer: ReturnType<typeof setTimeout> | null = null;
  private nudged = false;
  /** Kokoro, once it has loaded, for a call that started on the lite voice while it loaded. */
  private upgrade: Voice | null = null;
  /** The device proved too slow for Kokoro mid-call: stay on the lite voice. */
  private downgraded = false;
  /** Server speech (Groq Orpheus), when that's the chosen voice. */
  private readonly orpheus: OrpheusVoice | null = null;
  /** Reply sentences gathered per turn, for voices that speak a whole reply at once. */
  private replyText = new Map<number, string[]>();
  private voice: Voice;

  /**
   * `choice` is a ready voice, or "orpheus" for server speech (with the browser voice as the
   * backup). `waitForKokoro`: the caller chose Kokoro but it was still loading, so the call
   * starts on the lite voice and moves to Kokoro once it's ready.
   */
  constructor(choice: Voice | "orpheus", { waitForKokoro = false } = {}) {
    if (choice === "orpheus") {
      const orpheus = new OrpheusVoice((id, text) =>
        this.socket?.send({ type: "tts.request", id, text }),
      );
      this.orpheus = orpheus;
      this.voice = new FallbackVoice(orpheus, new LiteVoice(), (reason) => {
        console.warn(`[voice] Groq Orpheus unavailable (${reason}); using the built-in voice`);
        store().setVoiceMode("lite");
      });
    } else {
      this.voice = choice;
    }
    const voice = this.voice;
    this.player = new SentencePlayer(voice, {
      onSpeakingChange: (speaking) => {
        store().setAgentSpeaking(speaking);
        if (speaking) this.clearSilence();
        else this.armSilence();
      },
      onFirstAudio: (turnId, ttsMs) => this.onFirstAudio(turnId, ttsMs),
    });
    if (waitForKokoro && voice.mode === "lite" && typeof Worker !== "undefined") {
      // The landing page lets the caller start before Kokoro is ready; switch over once it is.
      loadKokoro().then(
        (kokoro) => {
          if (kokoroPreferred()) this.upgrade = kokoro;
        },
        () => undefined, // Kokoro can't load here: the lite voice stays.
      );
    }
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
      onSpeechAudio: (header, pcm) => this.orpheus?.onAudio(header.id, header.sample_rate, pcm),
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
    this.switchToLoadedKokoro();
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
        if (event.turn_id < store().currentTurnId) break;
        if (this.voice.wholeTurns) {
          // One speech request per reply: gather the sentences until the reply is done.
          this.replyText.set(event.turn_id, [...(this.replyText.get(event.turn_id) ?? []), event.text]);
        } else {
          this.player.enqueue(event.turn_id, event.index, event.text);
        }
        break;
      case "agent.text.done": {
        this.clearFiller();
        const reply = this.replyText.get(event.turn_id);
        this.replyText.delete(event.turn_id);
        if (reply && event.turn_id >= store().currentTurnId) {
          this.player.enqueue(event.turn_id, 0, reply.join(" "));
        }
        this.player.markDone(event.turn_id);
        break;
      }
      case "tts.done":
        this.orpheus?.onDone(event.id);
        break;
      case "tts.failed":
        this.orpheus?.onFailed(event.id, event.code, event.message);
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
    this.speechStartedAt = performance.now();
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
    this.switchToLoadedKokoro();

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
      // From the caller's first word to silence; includes the BARGE_IN_MIN_MS wait. A typed
      // message interrupts at once, so it has no speech start to measure from.
      ...(this.utterance ? { stop_ms: Math.round(performance.now() - this.speechStartedAt) } : {}),
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
      this.downgraded = true;
      this.voice = new LiteVoice();
      this.player.setVoice(this.voice);
      store().setVoiceMode("lite");
    }
  }

  /**
   * Between replies (the caller just finished a turn, so Mia is silent), move a call that
   * started on the lite voice over to Kokoro once it has loaded. Never mid-reply, so one reply
   * never mixes two voices, and never after the device proved too slow for Kokoro.
   */
  private switchToLoadedKokoro(): void {
    const ready = shouldSwitchToKokoro({
      kokoroReady: this.upgrade !== null,
      downgraded: this.downgraded,
      mode: this.voice.mode,
      speaking: this.player.isSpeaking,
    });
    if (!ready || !this.upgrade) return;
    this.voice = this.upgrade;
    this.upgrade = null;
    this.player.setVoice(this.voice);
    store().setVoiceMode("kokoro");
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
