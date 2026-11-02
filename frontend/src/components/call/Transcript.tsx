"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef } from "react";

import { useCallStore } from "@/store/callStore";

export function Transcript() {
  const transcript = useCallStore((s) => s.transcript);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [transcript]);

  return (
    <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4" aria-live="polite" aria-label="Live transcript">
      {transcript.length === 0 && (
        <p className="pt-8 text-center text-sm text-ink-muted">Connecting you to Mia...</p>
      )}
      <AnimatePresence initial={false}>
        {transcript.map((entry) =>
          entry.role === "system" ? (
            <motion.p
              key={entry.id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-center text-xs font-medium text-ink-muted"
            >
              {entry.text}
            </motion.p>
          ) : (
            <motion.div
              key={entry.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className={`flex ${entry.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                  entry.role === "user"
                    ? "rounded-br-sm bg-brand text-brand-ink"
                    : "rounded-bl-sm bg-surface-muted"
                }`}
              >
                {entry.text}
                {entry.interrupted && (
                  <span className="ml-1 text-xs opacity-70" title="Interrupted by the caller">
                    ⚡ cut off
                  </span>
                )}
              </div>
            </motion.div>
          ),
        )}
      </AnimatePresence>
      <div ref={end} />
    </div>
  );
}
