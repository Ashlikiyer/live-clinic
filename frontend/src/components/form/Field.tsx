"use client";

import { motion } from "motion/react";

import { formatFormValue } from "@/lib/time";
import type { FormValue } from "@/store/reducer";

interface FieldProps {
  field: string;
  label: string;
  required?: boolean;
  value?: FormValue;
}

export function Field({ field, label, required, value }: FieldProps) {
  return (
    <motion.div
      // Re-mount on each update so the glow replays.
      key={value?.updatedAt ?? "empty"}
      className="rounded-xl border border-line px-3 py-2"
      initial={value ? { backgroundColor: "var(--glow)" } : false}
      animate={{ backgroundColor: "rgba(0,0,0,0)" }}
      transition={{ duration: 1.2, ease: "easeOut" }}
    >
      <dt className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
        {label}
        {required && <span className="text-danger" aria-label="required">*</span>}
        {value && (
          <span className="ml-auto normal-case tracking-normal text-brand">
            {value.corrected ? (
              <span className="rounded bg-amber-100 px-1.5 py-0.5 font-semibold text-amber-800 dark:bg-amber-900 dark:text-amber-100">
                corrected
              </span>
            ) : (
              "heard from caller"
            )}
          </span>
        )}
      </dt>
      <dd className={`mt-0.5 min-h-5 text-sm ${value ? "font-medium" : "text-ink-muted/60"}`}>
        {value ? formatFormValue(field, value.value) : "—"}
      </dd>
    </motion.div>
  );
}
