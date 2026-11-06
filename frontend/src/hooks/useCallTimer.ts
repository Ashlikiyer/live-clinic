"use client";

import { useEffect, useState } from "react";

import { callClock } from "@/lib/deskStatus";
import { useCallStore } from "@/store/callStore";

/** "02:34" since the call started; stops when it ends. */
export function useCallTimer(): string {
  const startedAt = useCallStore((s) => s.startedAt);
  const endedAt = useCallStore((s) => s.endedAt);
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    if (endedAt !== null) return;
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [endedAt]);

  if (startedAt === null) return callClock(0);
  return callClock(((endedAt ?? now ?? startedAt) - startedAt) / 1000);
}
