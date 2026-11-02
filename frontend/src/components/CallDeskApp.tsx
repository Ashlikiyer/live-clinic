"use client";

import { MotionConfig } from "motion/react";
import { useCallback, useEffect, useRef } from "react";

import { CallDesk } from "@/components/CallDesk";
import { Landing } from "@/components/Landing";
import { SummaryCard } from "@/components/summary/SummaryCard";
import { callStats } from "@/lib/stats";
import { clinicDate } from "@/lib/time";
import { playDemo } from "@/mock/playDemo";
import { useCallStore } from "@/store/callStore";
import { latestConfirmed } from "@/store/reducer";

export function CallDeskApp() {
  const status = useCallStore((s) => s.status);
  const stopDemo = useRef<(() => void) | null>(null);

  const start = useCallback(() => {
    stopDemo.current?.();
    const now = Date.now();
    useCallStore.getState().startCall(now);
    stopDemo.current = playDemo(clinicDate(new Date(now)));
  }, []);

  const end = useCallback(() => {
    stopDemo.current?.();
    stopDemo.current = null;
    const store = useCallStore.getState();
    if (store.status === "ended") return;
    const now = Date.now();
    // Phase 0 only: the server sends call.ended once the socket is wired up.
    store.applyEvent({
      type: "call.ended",
      ts: now,
      outcome: latestConfirmed(store.appointments) ? "booked" : "abandoned",
      summary: "The caller ended the call.",
      stats: callStats(store.metrics, (now - (store.startedAt ?? now)) / 1000),
    });
  }, []);

  const callAgain = useCallback(() => {
    useCallStore.getState().reset();
    start();
  }, [start]);

  useEffect(() => () => stopDemo.current?.(), []);

  return (
    <MotionConfig reducedMotion="user">
      {status === "idle" ? (
        <Landing onCall={start} />
      ) : (
        <>
          <CallDesk onEnd={end} />
          {status === "ended" && (
            <SummaryCard onCallAgain={callAgain} onClose={() => useCallStore.getState().reset()} />
          )}
        </>
      )}
    </MotionConfig>
  );
}
