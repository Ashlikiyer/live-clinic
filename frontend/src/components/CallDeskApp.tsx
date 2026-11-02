"use client";

import { MotionConfig } from "motion/react";
import { useCallback, useEffect, useRef } from "react";

import { CallDesk, type CallControls } from "@/components/CallDesk";
import { Landing } from "@/components/Landing";
import { SummaryCard } from "@/components/summary/SummaryCard";
import { callStats } from "@/lib/stats";
import { clinicDate } from "@/lib/time";
import { playDemo } from "@/mock/playDemo";
import { setCalendarSource } from "@/realtime/calendarSource";
import { LiveCall } from "@/realtime/liveCall";
import { useCallStore } from "@/store/callStore";
import { latestConfirmed } from "@/store/reducer";
import type { Voice } from "@/voice/player";
import { LiteVoice, getAudioContext, kokoroPreferred, loadKokoro } from "@/voice/tts";

/**
 * Kokoro if it has loaded and this device can synthesize faster than real time; otherwise the
 * zero-download lite voice, so the call starts now and stays responsive.
 */
async function pickVoice(useKokoro: boolean): Promise<Voice> {
  if (useKokoro || !LiteVoice.available()) return loadKokoro();
  return new LiteVoice();
}

export function CallDeskApp() {
  const status = useCallStore((s) => s.status);
  const kind = useCallStore((s) => s.kind);
  const live = useRef<LiveCall | null>(null);
  const stopDemo = useRef<(() => void) | null>(null);

  const stopAll = useCallback(() => {
    live.current?.dispose();
    live.current = null;
    stopDemo.current?.();
    stopDemo.current = null;
  }, []);

  const startLive = useCallback(
    async (useKokoro: boolean) => {
      stopAll();
      // Create the audio context inside the click so the browser allows playback.
      getAudioContext();
      const call = new LiveCall(await pickVoice(useKokoro));
      live.current = call;
      await call.start();
    },
    [stopAll],
  );

  const startDemo = useCallback(() => {
    stopAll();
    setCalendarSource(null);
    const now = Date.now();
    useCallStore.getState().startCall(now, "demo");
    stopDemo.current = playDemo(clinicDate(new Date(now)));
  }, [stopAll]);

  const endDemo = useCallback(() => {
    stopAll();
    const store = useCallStore.getState();
    if (store.status === "ended") return;
    const now = Date.now();
    store.applyEvent({
      type: "call.ended",
      ts: now,
      outcome: latestConfirmed(store.appointments) ? "booked" : "abandoned",
      summary: "The caller ended the demo call.",
      stats: callStats(store.metrics, (now - (store.startedAt ?? now)) / 1000),
    });
  }, [stopAll]);

  const controls: CallControls = {
    onEnd: () => (kind === "live" ? void live.current?.end() : endDemo()),
    onSendText: kind === "live" ? (text) => live.current?.sendText(text) : null,
    onTyping: () => live.current?.callerActive(),
    onToggleMute: () => {
      const muted = !useCallStore.getState().muted;
      if (kind === "live") void live.current?.setMuted(muted);
      else useCallStore.getState().setMuted(muted);
    },
  };

  const backToStart = useCallback(() => {
    stopAll();
    useCallStore.getState().reset();
  }, [stopAll]);

  useEffect(() => stopAll, [stopAll]);

  return (
    <MotionConfig reducedMotion="user">
      {status === "idle" ? (
        <Landing onCall={(ready) => void startLive(ready)} onDemo={startDemo} />
      ) : (
        <>
          <CallDesk controls={controls} />
          {status === "ended" && (
            <SummaryCard
              onCallAgain={() => {
                backToStart();
                if (kind === "demo") startDemo();
                else void startLive(kokoroPreferred());
              }}
              onClose={backToStart}
            />
          )}
        </>
      )}
    </MotionConfig>
  );
}
