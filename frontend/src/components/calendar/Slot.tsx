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

const tile = "flex min-w-0 flex-col justify-center overflow-hidden whitespace-nowrap rounded-[10px] px-2.5";

const KIND_CLASS: Record<AppointmentState, string> = {
  holding: "z-10 border border-holding-line bg-holding text-holding-ink animate-hold",
  confirmed: "z-10 border border-confirmed-line bg-confirmed text-confirmed-ink",
  cancelled: "z-10 border border-cancelled-line bg-cancelled text-cancelled-ink line-through opacity-75",
};

const KIND_TEXT: Record<AppointmentState, { label: string; sub?: string }> = {
  holding: { label: "Holding for you", sub: "Waiting for your yes" },
  confirmed: { label: "Booked" },
  cancelled: { label: "Released" },
};

export function Slot({ kind, style, label, time, offered, offeredAt, layoutId }: SlotProps) {
  if (kind === "free") {
    return (
      <motion.div
        key={offered ? `offered-${offeredAt}` : "free"}
        className={`${tile} ${offered ? "z-[2] border border-dashed border-ink bg-bg" : "border border-line bg-surface"}`}
        style={style}
        initial={offered ? { scale: 0.94, opacity: 0.4 } : false}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.3 }}
        aria-label={offered ? "Offered by Mia" : undefined}
      >
        {offered && (
          <>
            <span className="truncate text-xs font-semibold">Available</span>
            <span className="truncate text-[10.5px] opacity-80">Offered by Mia</span>
          </>
        )}
      </motion.div>
    );
  }

  if (kind === "busy") {
    return <div className="z-[1] rounded-[10px] bg-busy" style={style} aria-label="Taken" />;
  }

  const text = KIND_TEXT[kind];
  const title = kind === "confirmed" && label ? label : text.label;
  const sub = kind === "holding" ? text.sub : time;
  return (
    <motion.div
      layout
      layoutId={layoutId}
      className={`${tile} transition-colors ${KIND_CLASS[kind]}`}
      style={style}
      initial={{ opacity: 0, scale: 0.94 }}
      animate={kind === "cancelled" ? { opacity: [1, 1, 0], scale: 1 } : { opacity: 1, scale: 1 }}
      transition={kind === "cancelled" ? { duration: 2.4, times: [0, 0.6, 1] } : { duration: 0.25 }}
    >
      <span className="truncate text-xs font-semibold">{title}</span>
      {sub && <span className="truncate text-[10.5px] opacity-80">{sub}</span>}
    </motion.div>
  );
}
