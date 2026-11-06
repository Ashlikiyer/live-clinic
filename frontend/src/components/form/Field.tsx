"use client";

import { useEffect, useState } from "react";

import { formatFormValue } from "@/lib/time";
import type { FormValue } from "@/store/reducer";

interface FieldProps {
  field: string;
  label: string;
  required?: boolean;
  value?: FormValue;
}

const GLOW_MS = 1500;

/** True for a moment after each update, so a freshly heard value glows. */
function useJustUpdated(updatedAt: number | undefined): boolean {
  const [glowing, setGlowing] = useState(false);
  useEffect(() => {
    if (updatedAt === undefined) return;
    const on = setTimeout(() => setGlowing(true), 0);
    const off = setTimeout(() => setGlowing(false), GLOW_MS);
    return () => {
      clearTimeout(on);
      clearTimeout(off);
    };
  }, [updatedAt]);
  return glowing;
}

export function Field({ field, label, required, value }: FieldProps) {
  const glowing = useJustUpdated(value?.updatedAt);
  return (
    <div
      className={`flex flex-col gap-1 rounded-[14px] border px-3.5 py-[11px] transition-[background,border-color,box-shadow] duration-300 ${
        glowing
          ? "border-ink bg-surface shadow-[0_0_0_4px_oklch(0.7_0.12_15/.18)]"
          : value
            ? "border-line bg-surface"
            : "border-line bg-bg"
      }`}
    >
      <dt className="flex items-center justify-between gap-2">
        <span className="text-[11.5px] text-ink-faint">
          {label}
          {required && (
            <span className="text-[oklch(0.55_0.16_15)]" aria-label="required">
              {" "}*
            </span>
          )}
        </span>
        {value &&
          (value.corrected ? (
            <span className="rounded-full bg-rose-soft px-[7px] py-0.5 text-[10.5px] font-medium text-rose-ink">
              Corrected
            </span>
          ) : (
            <span className="text-[10.5px] text-ink-faint">From your call</span>
          ))}
      </dt>
      <dd className={`text-sm ${value ? "font-medium text-ink" : "text-[#c4c4c0]"}`}>
        {value ? formatFormValue(field, value.value) : "—"}
      </dd>
    </div>
  );
}
