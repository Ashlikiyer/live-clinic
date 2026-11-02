"use client";

import { useEffect, useState } from "react";

import { CLINIC_NAME } from "@/lib/clinic";

type BackendState = "waking" | "ready" | "offline";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

const BACKEND_LABEL: Record<BackendState, string> = {
  waking: "Waking up the clinic...",
  ready: "Clinic line is open",
  offline: "Backend offline: the scripted demo still works",
};

export function Landing({ onCall }: { onCall: () => void }) {
  const backend = useBackendWake();

  return (
    <main className="flex flex-1 items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg rounded-3xl border border-line bg-surface p-8 text-center shadow-sm sm:p-10">
        <div className="mx-auto mb-6 flex size-14 items-center justify-center rounded-2xl bg-brand-soft text-2xl text-brand">
          +
        </div>
        <h1 className="text-3xl font-semibold tracking-tight">{CLINIC_NAME}</h1>
        <p className="mt-3 text-ink-muted">
          Talk to Mia, our AI receptionist. Watch her book your visit on the live calendar and
          fill in your intake form as you speak.
        </p>

        <button
          type="button"
          onClick={onCall}
          className="mt-8 inline-flex w-full items-center justify-center gap-2 rounded-full bg-brand px-8 py-4 text-lg font-semibold text-brand-ink shadow-sm transition hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand sm:w-auto"
        >
          <span aria-hidden>📞</span> Call the clinic
        </button>

        <p className="mt-6 rounded-xl bg-surface-muted px-4 py-3 text-sm text-ink-muted">
          Demo only. Uses fake data. Don&apos;t share real medical information.
        </p>

        <p className="mt-4 flex items-center justify-center gap-2 text-xs text-ink-muted" aria-live="polite">
          <span
            className={`size-2 rounded-full ${
              backend === "ready" ? "bg-green-500" : backend === "waking" ? "bg-amber-400" : "bg-ink-muted"
            }`}
          />
          {BACKEND_LABEL[backend]}
        </p>
        <p className="mt-2 text-xs text-ink-muted">
          Preview build: plays a scripted demo call (voice arrives in Phase 1). Headphones
          recommended.
        </p>
      </div>
    </main>
  );
}
