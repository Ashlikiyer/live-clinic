"use client";

import { useEffect, useRef } from "react";

import { useCallStore } from "@/store/callStore";

export function Transcript() {
  const transcript = useCallStore((s) => s.transcript);
  const speaking = useCallStore((s) => s.agentSpeaking);
  const end = useRef<HTMLDivElement>(null);
  const lastAgent = transcript.findLast((e) => e.role === "agent")?.id;

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [transcript]);

  return (
    <div
      className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto px-3.5 pb-3.5 pt-2.5"
      aria-live="polite"
      aria-label="Live transcript"
    >
      {transcript.length === 0 && <p className="m-auto text-[13px] text-ink-ghost">Connecting to Mia…</p>}
      {transcript.map((entry) =>
        entry.role === "system" ? (
          <div key={entry.id} className="animate-in flex items-center gap-2 px-1 text-[11.5px] text-ink-faint">
            <span className="h-px flex-1 bg-line" />
            {entry.text}
            <span className="h-px flex-1 bg-line" />
          </div>
        ) : entry.role === "user" ? (
          <div key={entry.id} className="animate-in flex justify-end">
            <div className="max-w-[85%] rounded-[16px_4px_16px_16px] bg-ink px-3.5 py-2.5 text-[13.5px] leading-[1.45] text-white">
              {entry.text}
            </div>
          </div>
        ) : (
          <div key={entry.id} className="animate-in flex flex-col items-start gap-1">
            <div className="max-w-[88%] rounded-[4px_16px_16px_16px] bg-surface-muted px-3.5 py-2.5 text-[13.5px] leading-[1.45]">
              {entry.text}
              {entry.unspoken && <span className="text-[#b5b5b9] line-through"> {entry.unspoken}</span>}
              {speaking && entry.id === lastAgent && !entry.interrupted && (
                <span
                  className="ml-0.5 inline-block h-3.5 w-0.5 bg-ink align-[-2px]"
                  style={{ animation: "lcd-caret .8s steps(1) infinite" }}
                  aria-hidden
                />
              )}
            </div>
            {entry.interrupted && (
              <span className="pl-1 text-[11px] font-medium text-rose-ink">You cut in, so Mia stopped</span>
            )}
          </div>
        ),
      )}
      <div ref={end} />
    </div>
  );
}
