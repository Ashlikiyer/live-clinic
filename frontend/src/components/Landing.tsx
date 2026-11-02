"use client";

import { useEffect, useState } from "react";

import { API_URL } from "@/lib/api";
import { CLINIC_NAME } from "@/lib/clinic";
import { loadKokoro, onKokoroStatus, type KokoroStatus } from "@/voice/tts";

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

/** Starts downloading and warming up the Kokoro voice right away (cached after the first visit). */
function useVoiceModel(): KokoroStatus {
  const [status, setStatus] = useState<KokoroStatus>({ state: "loading", progress: 0 });
  useEffect(() => {
    const unsubscribe = onKokoroStatus(setStatus);
    loadKokoro().catch(() => undefined);
    return unsubscribe;
  }, []);
  return status;
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
  onCall: (useKokoro: boolean) => void;
  onDemo: () => void;
}) {
  const backend = useBackendWake();
  const voice = useVoiceModel();
  const useKokoro = voice.state === "ready" && !voice.tooSlow; // same rule as kokoroPreferred()

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
          onClick={() => onCall(useKokoro)}
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

        <div className="mt-6 text-left" aria-live="polite">
          {voice.state === "loading" && (
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
          {voice.state === "ready" && voice.tooSlow && (
            <p className="text-xs text-ink-muted">
              This device is a bit slow for Mia&apos;s natural voice, so she&apos;ll use your
              browser&apos;s built-in voice to keep replies quick.
            </p>
          )}
          {voice.state === "failed" && (
            <p className="text-xs text-ink-muted">
              Mia&apos;s natural voice couldn&apos;t load on this device, so she&apos;ll use your
              browser&apos;s built-in voice.
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
