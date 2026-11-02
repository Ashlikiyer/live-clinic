"use client";

import { FORM_FIELDS } from "@/lib/clinic";
import { useCallStore } from "@/store/callStore";
import { missingRequiredFields } from "@/store/reducer";

import { Field } from "./Field";

export function IntakeForm() {
  const form = useCallStore((s) => s.form);
  const missing = missingRequiredFields(form);

  return (
    <section
      aria-label="Patient intake form"
      className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-line bg-surface"
    >
      <div className="flex items-baseline justify-between border-b border-line px-4 py-3">
        <h2 className="font-semibold">Intake form</h2>
        <p className="text-xs text-ink-muted">
          {missing.length === 0 ? "Ready to book" : `${missing.length} required left`}
        </p>
      </div>
      <dl className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
        {FORM_FIELDS.map(({ field, label, required }) => (
          <Field key={field} field={field} label={label} required={required} value={form[field]} />
        ))}
      </dl>
    </section>
  );
}
