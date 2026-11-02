import { callStats } from "@/lib/stats";
import { useCallStore } from "@/store/callStore";

import { demoKeepFree } from "./busy";
import { buildDemoScript, type DemoStep } from "./demoCall";

/** Plays the scripted demo call into the store. Returns a function that stops it. */
export function playDemo(today: string): () => void {
  const script = buildDemoScript(today);
  demoKeepFree.clear();
  script.freeKeys.forEach((key) => demoKeepFree.add(key));

  const run = (step: DemoStep) => {
    const store = useCallStore.getState();
    const now = Date.now();
    switch (step.kind) {
      case "event":
        if (step.event.type === "call.ended") {
          // The real server computes these; the mock derives them from what was shown.
          const duration = (now - (store.startedAt ?? now)) / 1000;
          store.applyEvent({ ...step.event, ts: now, stats: callStats(store.metrics, duration) });
        } else {
          store.applyEvent({ ...step.event, ts: now });
        }
        break;
      case "speaking":
        store.setAgentSpeaking(step.speaking);
        break;
      case "mic":
        store.setMicLevel(store.muted ? 0 : step.level);
        break;
      case "interrupt":
        store.interrupt(step.turnId, step.playedText);
        break;
    }
  };

  const timers = script.steps.map((step) => setTimeout(() => run(step), step.at));
  return () => timers.forEach(clearTimeout);
}
