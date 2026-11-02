"use client";

import { motion } from "motion/react";

import { FORM_FIELDS } from "@/lib/clinic";
import {
  dateOf,
  formatDuration,
  formatFormValue,
  formatLongDate,
  formatMs,
  formatTime,
} from "@/lib/time";
import { transcriptText } from "@/lib/transcript";
import type { CallOutcome } from "@/realtime/events";
import { useCallStore } from "@/store/callStore";
import { latestConfirmed } from "@/store/reducer";

const OUTCOME_LABEL: Record<CallOutcome, string> = {
  booked: "Appointment booked",
  rescheduled: "Appointment rescheduled",
  cancelled: "Appointment cancelled",
  info_only: "Information only",
  transferred: "Transferred to staff",
  emergency_advised: "Emergency care advised",
  abandoned: "Call ended early",
};

function download(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function SummaryCard({ onCallAgain, onClose }: { onCallAgain: () => void; onClose: () => void }) {
  const ended = useCallStore((s) => s.ended);
  const form = useCallStore((s) => s.form);
  const transcript = useCallStore((s) => s.transcript);
  const appointment = useCallStore((s) => latestConfirmed(s.appointments));
  const doctors = useCallStore((s) => s.doctors);
  if (!ended) return null;

  const { stats } = ended;
  const doctor = appointment ? doctors.find((d) => d.id === appointment.doctorId) : undefined;
  const filled = FORM_FIELDS.filter(({ field }) => form[field]);
  const statItems = [
    { label: "Call length", value: formatDuration(stats.duration_s) },
    { label: "Replies", value: String(stats.turn_count) },
    { label: "Median reply", value: stats.median_reply_ms === null ? "—" : formatMs(stats.median_reply_ms) },
    { label: "Slowest reply", value: stats.slowest_reply_ms === null ? "—" : formatMs(stats.slowest_reply_ms) },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center" role="dialog" aria-modal="true" aria-labelledby="summary-title">
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-3xl bg-surface p-6 shadow-xl"
      >
        <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">Call summary</p>
        <h2 id="summary-title" className="mt-1 text-2xl font-semibold">
          {OUTCOME_LABEL[ended.outcome]}
        </h2>
        <p className="mt-2 text-sm text-ink-muted">{ended.summary}</p>

        {appointment && (
          <div className="mt-4 rounded-2xl bg-confirmed p-4 text-confirmed-ink">
            <p className="font-semibold">{doctor?.name ?? appointment.doctorId}</p>
            <p className="text-sm">
              {formatLongDate(dateOf(appointment.start))} at {formatTime(appointment.start)}
            </p>
          </div>
        )}

        <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {statItems.map((item) => (
            <div key={item.label} className="rounded-xl bg-surface-muted p-3">
              <dt className="text-[11px] text-ink-muted">{item.label}</dt>
              <dd className="font-semibold tabular-nums">{item.value}</dd>
            </div>
          ))}
        </dl>

        {filled.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-semibold">Intake form</h3>
            <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              {filled.map(({ field, label }) => (
                <div key={field} className="contents">
                  <dt className="text-ink-muted">{label}</dt>
                  <dd>{formatFormValue(field, form[field]?.value ?? "")}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        <div className="mt-6 flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            onClick={onCallAgain}
            className="flex-1 rounded-full bg-brand px-4 py-2.5 font-semibold text-brand-ink hover:opacity-90"
          >
            Call again
          </button>
          <button
            type="button"
            onClick={() =>
              download(
                "bayview-call-transcript.txt",
                transcriptText(transcript, [`Outcome: ${OUTCOME_LABEL[ended.outcome]}`, ended.summary]),
              )
            }
            className="flex-1 rounded-full border border-line px-4 py-2.5 font-medium hover:bg-surface-muted"
          >
            Download transcript
          </button>
        </div>
        <button type="button" onClick={onClose} className="mt-3 w-full text-sm text-ink-muted hover:underline">
          Back to start
        </button>
      </motion.div>
    </div>
  );
}
