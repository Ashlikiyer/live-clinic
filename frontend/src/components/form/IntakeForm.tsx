"use client";

import { FORM_FIELDS } from "@/lib/clinic";
import { useCallStore } from "@/store/callStore";
import { missingRequiredFields } from "@/store/reducer";

import { Field } from "./Field";

const REQUIRED = FORM_FIELDS.filter((f) => f.required).length;

export function IntakeForm() {
  const form = useCallStore((s) => s.form);
  const done = REQUIRED - missingRequiredFields(form).length;

  return (
    <section aria-label="Patient intake form" className="flex h-full min-h-0 flex-col overflow-hidden rounded-3xl border border-line bg-surface">
      <div className="flex flex-col gap-3 px-5 pb-3.5 pt-5">
        <div className="flex items-end justify-between">
          <div className="flex flex-col gap-1">
            <span className="text-xs text-ink-faint">Patient intake</span>
            <h2 className="text-[26px] font-medium leading-none tracking-[-0.035em]">Your details</h2>
          </div>
          <span className="text-xs font-medium text-ink-muted">
            {done} of {REQUIRED} required
          </span>
        </div>
        <div
          className="h-1 overflow-hidden rounded-full bg-line"
          role="progressbar"
          aria-label="Required details collected"
          aria-valuemin={0}
          aria-valuemax={REQUIRED}
          aria-valuenow={done}
        >
          <div className="h-full bg-ink transition-[width] duration-300" style={{ width: `${(done / REQUIRED) * 100}%` }} />
        </div>
      </div>
      <dl className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto px-3.5 pb-3.5 pt-1">
        {FORM_FIELDS.map(({ field, label, required }) => (
          <Field key={field} field={field} label={label} required={required} value={form[field]} />
        ))}
      </dl>
      <p className="border-t border-line px-5 py-3 text-[11.5px] leading-[1.45] text-ink-ghost">
        Filled from what you say. Deleted after 24 hours.
      </p>
    </section>
  );
}
