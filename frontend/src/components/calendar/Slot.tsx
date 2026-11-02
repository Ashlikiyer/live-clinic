"use client";

import { motion } from "motion/react";
import type { CSSProperties } from "react";

import { OPEN_MINUTES, SLOT_MINUTES } from "@/lib/clinic";
import type { AppointmentState } from "@/store/reducer";

type SlotKind = "free" | "busy" | AppointmentState;

/** CSS grid position for a doctor column (0-based) and a time range in minutes. */
export function gridPlacement(column: number, startMinutes: number, durationMinutes: number): CSSProperties {
  return {
    gridColumn: column + 2,
    gridRow: `${(startMinutes - OPEN_MINUTES) / SLOT_MINUTES + 1} / span ${Math.max(1, durationMinutes / SLOT_MINUTES)}`,
  };
}

interface SlotProps {
  kind: SlotKind;
  style: CSSProperties;
  label?: string;
  time?: string;
  offered?: boolean;
  offeredAt?: number;
  layoutId?: string;
}

const KIND_CLASS: Record<Exclude<SlotKind, "free">, string> = {
  busy: "z-[1] bg-busy text-busy-ink",
  holding: "z-10 bg-holding text-holding-ink animate-hold ring-2 ring-amber-400",
  confirmed: "z-10 bg-confirmed text-confirmed-ink ring-1 ring-green-500/50",
  cancelled: "z-10 bg-cancelled text-cancelled-ink line-through",
};

const KIND_LABEL: Record<Exclude<SlotKind, "free" | "busy">, string> = {
  holding: "Holding",
  confirmed: "Confirmed",
  cancelled: "Cancelled",
};

export function Slot({ kind, style, label, time, offered, offeredAt, layoutId }: SlotProps) {
  if (kind === "free") {
    return (
      <motion.div
        key={offered ? `offered-${offeredAt}` : "free"}
        className={`rounded-lg border border-dashed ${offered ? "z-[2] border-offered bg-sky-400/15" : "border-line"}`}
        style={style}
        initial={offered ? { scale: 0.92, opacity: 0.4 } : false}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.3 }}
        aria-label={offered ? "Offered slot" : undefined}
      />
    );
  }

  if (kind === "busy") {
    return <div className={`rounded-lg ${KIND_CLASS.busy}`} style={style} aria-label="Busy" />;
  }

  return (
    <motion.div
      layout
      layoutId={layoutId}
      className={`flex min-w-0 flex-col justify-center overflow-hidden rounded-lg px-2 text-xs ${KIND_CLASS[kind]}`}
      style={style}
      initial={{ opacity: 0, scale: 0.9 }}
      animate={kind === "cancelled" ? { opacity: [1, 1, 0], scale: 1 } : { opacity: 1, scale: 1 }}
      transition={kind === "cancelled" ? { duration: 2.4, times: [0, 0.6, 1] } : { duration: 0.25 }}
    >
      <span className="truncate font-semibold">{label ?? KIND_LABEL[kind]}</span>
      {time && <span className="truncate opacity-80">{time}</span>}
    </motion.div>
  );
}
