"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import { API_URL } from "@/lib/api";
import { CLINIC_NAME } from "@/lib/clinic";
import { DEFAULT_VOICE, VOICE_CHOICES, parseVoiceChoice, type VoiceChoice } from "@/voice/choice";
import { loadKokoro, onKokoroStatus, type KokoroStatus } from "@/voice/tts";

const VOICE_KEY = "mia-voice";

type BackendState = "waking" | "ready" | "offline";

/** Wakes the backend (Render free tier sleeps) as soon as the landing page opens. */
function useBackendWake(): BackendState {
  const [state, setState] = useState<BackendState>("waking");
  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60_000);
    fetch(`${API_URL}/api/health`, { signal: controller.signal })
      .then((res) => setState(res.ok ? "ready" : "offline"))
      .catch(() => setState("offline"))
      .finally(() => clearTimeout(timeout));
    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, []);
  return state;
}

/** Downloads and warms up Kokoro only when it's the chosen voice (cached after the first time). */
function useVoiceModel(enabled: boolean): KokoroStatus {
  const [status, setStatus] = useState<KokoroStatus>({ state: "loading", progress: 0 });
  useEffect(() => {
    if (!enabled) return;
    const unsubscribe = onKokoroStatus(setStatus);
    loadKokoro().catch(() => undefined);
    return unsubscribe;
  }, [enabled]);
  return status;
}

// The caller's voice choice, remembered in this browser. Kept in memory too, so choosing still
// works when storage is blocked.
let chosenVoice: VoiceChoice | null = null;
const voiceListeners = new Set<() => void>();

function readVoiceChoice(): VoiceChoice {
  if (chosenVoice) return chosenVoice;
  try {
    return parseVoiceChoice(localStorage.getItem(VOICE_KEY));
  } catch {
    return DEFAULT_VOICE;
  }
}

function useVoiceChoice(): [VoiceChoice, (choice: VoiceChoice) => void] {
  const choice = useSyncExternalStore(
    (listener) => {
      voiceListeners.add(listener);
      return () => voiceListeners.delete(listener);
    },
    readVoiceChoice,
    () => DEFAULT_VOICE,
  );
  const choose = (next: VoiceChoice) => {
    chosenVoice = next;
    try {
      localStorage.setItem(VOICE_KEY, next);
    } catch {
      // Storage blocked: the choice lasts until the page closes.
    }
    voiceListeners.forEach((listener) => listener());
  };
  return [choice, choose];
}

const BACKEND_LABEL: Record<BackendState, string> = {
  waking: "Waking up the clinic...",
  ready: "Clinic line is open",
  offline: "The clinic is offline right now. You can still watch the demo.",
};

export function Landing({
  onCall,
  onDemo,
}: {
  onCall: (voice: VoiceChoice) => void;
  onDemo: () => void;
}) {
  const backend = useBackendWake();
  const [choice, setChoice] = useVoiceChoice();
  const voice = useVoiceModel(choice === "kokoro");

  return (
    <main className="flex flex-1 items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg rounded-3xl border border-line bg-surface p-8 text-center shadow-sm sm:p-10">
        <div className="mx-auto mb-6 flex size-14 items-center justify-center rounded-2xl bg-brand-soft text-2xl text-brand">
          +
        </div>
        <h1 className="text-3xl font-semibold tracking-tight">{CLINIC_NAME}</h1>
        <p className="mt-3 text-ink-muted">
          Talk to Mia, our AI receptionist. Ask about the clinic or request a visit, and interrupt
          her any time, just like a real call.
        </p>

        <button
          type="button"
          onClick={() => onCall(choice)}
          disabled={backend === "offline"}
          className="mt-8 inline-flex w-full items-center justify-center gap-2 rounded-full bg-brand px-8 py-4 text-lg font-semibold text-brand-ink shadow-sm transition hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50 sm:w-auto"
        >
          <span aria-hidden>📞</span> Call the clinic
        </button>
        <button
          type="button"
          onClick={onDemo}
          className="mt-3 block w-full text-sm font-medium text-brand hover:underline"
        >
          or watch a scripted demo call
        </button>

        <fieldset className="mt-6 text-left">
          <legend className="text-xs font-medium text-ink-muted">Mia&apos;s voice</legend>
          <div className="mt-1.5 grid grid-cols-3 gap-1 rounded-full bg-surface-muted p-1">
            {VOICE_CHOICES.map((option) => (
              <label
                key={option.value}
                className={`cursor-pointer rounded-full px-2 py-1.5 text-center text-sm font-medium transition has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand ${
                  choice === option.value ? "bg-surface text-ink shadow-sm" : "text-ink-muted hover:text-ink"
                }`}
              >
                <input
                  type="radio"
                  name="voice"
                  value={option.value}
                  checked={choice === option.value}
                  onChange={() => setChoice(option.value)}
                  className="sr-only"
                />
                {option.label}
              </label>
            ))}
          </div>
          <p className="mt-1.5 text-[11px] text-ink-muted">
            {VOICE_CHOICES.find((option) => option.value === choice)?.hint}
          </p>
        </fieldset>

        <div className="mt-4 text-left" aria-live="polite">
          {choice === "kokoro" && voice.state === "loading" && (
            <>
              <div className="flex justify-between text-xs text-ink-muted">
                <span>Loading Mia&apos;s voice (first visit only)</span>
                <span className="tabular-nums">{Math.round(voice.progress * 100)}%</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-muted">
                <div
                  className="h-full rounded-full bg-brand transition-[width] duration-300"
                  style={{ width: `${Math.max(3, voice.progress * 100)}%` }}
                />
              </div>
              <p className="mt-1 text-[11px] text-ink-muted">
                You can call now; Mia will use a simpler voice until this finishes.
              </p>
            </>
          )}
          {choice === "kokoro" && voice.state === "ready" && voice.tooSlow && (
            <p className="text-xs text-ink-muted">
              This device is a bit slow for the in-browser voice, so Mia will use your
              browser&apos;s built-in voice. Pick &ldquo;Natural&rdquo; for a human-sounding voice.
            </p>
          )}
          {choice === "kokoro" && voice.state === "failed" && (
            <p className="text-xs text-ink-muted">
              The in-browser voice couldn&apos;t run on this device, so Mia will use your
              browser&apos;s built-in voice. Pick &ldquo;Natural&rdquo; for a human-sounding voice.
            </p>
          )}
        </div>

        <p className="mt-6 rounded-xl bg-surface-muted px-4 py-3 text-sm text-ink-muted">
          Demo only. Uses fake data. Don&apos;t share real medical information. Your speech is
          transcribed by Groq and not stored as audio.
        </p>

        <p className="mt-4 flex items-center justify-center gap-2 text-xs text-ink-muted" aria-live="polite">
          <span
            className={`size-2 rounded-full ${
              backend === "ready" ? "bg-green-500" : backend === "waking" ? "bg-amber-400" : "bg-ink-muted"
            }`}
          />
          {BACKEND_LABEL[backend]}
        </p>
        <p className="mt-2 text-xs text-ink-muted">Headphones recommended, so Mia doesn&apos;t hear herself.</p>
      </div>
    </main>
  );
}
