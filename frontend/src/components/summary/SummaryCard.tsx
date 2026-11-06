"use client";

import { motion } from "motion/react";

import { fetchTranscript } from "@/lib/api";
import { isBusyEnding } from "@/lib/busy";
import { FORM_FIELDS } from "@/lib/clinic";
import { callClock } from "@/lib/deskStatus";
import { dateOf, formatFormValue, formatLongDate, formatTime, minutesOf } from "@/lib/time";
import { transcriptText } from "@/lib/transcript";
import type { CallOutcome } from "@/realtime/events";
import { useCallStore } from "@/store/callStore";
import { latestConfirmed } from "@/store/reducer";

/** The big headline and the small status pill for each outcome. */
const OUTCOME: Record<CallOutcome, { title: string; pill: string; tone: "good" | "alert" | "plain" }> = {
  booked: { title: "You're booked.", pill: "Booked", tone: "good" },
  rescheduled: { title: "Moved for you.", pill: "Rescheduled", tone: "good" },
  cancelled: { title: "Cancelled.", pill: "Cancelled", tone: "plain" },
  info_only: { title: "Call ended.", pill: "No booking", tone: "plain" },
  transferred: { title: "Passed to the front desk.", pill: "Transferred", tone: "plain" },
  emergency_advised: { title: "Please get help now.", pill: "Emergency advised", tone: "alert" },
  abandoned: { title: "Call ended.", pill: "No booking", tone: "plain" },
};

const BUSY_OUTCOME = { title: "Mia's line is busy.", pill: "Busy", tone: "alert" } as const;

const PILL_TONE = {
  good: "bg-confirmed text-confirmed-ink",
  alert: "bg-rose-soft text-rose-ink",
  plain: "bg-surface text-ink-muted",
};

function download(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

const secondaryButton =
  "h-12 rounded-full border border-line-strong bg-surface px-6 text-sm font-medium transition-colors hover:bg-surface-muted";

export function SummaryCard({ onCallAgain, onClose }: { onCallAgain: () => void; onClose: () => void }) {
  const ended = useCallStore((s) => s.ended);
  const form = useCallStore((s) => s.form);
  const transcript = useCallStore((s) => s.transcript);
  const kind = useCallStore((s) => s.kind);
  const callId = useCallStore((s) => s.callId);
  const appointment = useCallStore((s) => latestConfirmed(s.appointments));
  const doctors = useCallStore((s) => s.doctors);
  if (!ended) return null;

  const busy = isBusyEnding(ended.outcome, ended.summary);
  const outcome = busy ? BUSY_OUTCOME : OUTCOME[ended.outcome];
  const doctor = appointment ? doctors.find((d) => d.id === appointment.doctorId) : undefined;
  const filled = FORM_FIELDS.filter(({ field }) => form[field]);
  const minutes = appointment ? minutesOf(appointment.end) - minutesOf(appointment.start) : 0;

  const downloadTranscript = async () => {
    const local = transcriptText(transcript, [`Outcome: ${outcome.pill}`, ended.summary]);
    // Live calls download the server's stored copy; the scripted demo (or a failure) uses
    // what is on screen.
    const text =
      kind === "live" && callId ? await fetchTranscript(callId).catch(() => local) : local;
    download("bayview-call-transcript.txt", text);
  };

  return (
    <motion.div
      className="fixed inset-0 z-50 grid place-items-center bg-[rgba(17,17,19,.25)] p-6 backdrop-blur-sm max-sm:p-3"
      role="dialog"
      aria-modal="true"
      aria-labelledby="summary-title"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="flex max-h-[calc(100dvh-48px)] w-[min(720px,100%)] flex-col gap-2.5 overflow-auto rounded-[28px] bg-surface p-2.5 shadow-[0_40px_80px_-30px_rgba(0,0,0,.35)]"
      >
        <div className="flex flex-col gap-[18px] rounded-[20px] bg-surface-muted px-6 pb-5 pt-[26px] max-sm:px-4">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[12.5px] text-ink-faint">Call summary · {callClock(ended.stats.duration_s)}</span>
            <span className={`rounded-full px-[11px] py-1 text-xs font-semibold ${PILL_TONE[outcome.tone]}`}>
              {outcome.pill}
            </span>
          </div>
          <h2 id="summary-title" className="text-[44px] font-medium leading-none tracking-[-0.045em] max-sm:text-[34px]">
            {outcome.title}
          </h2>
          {appointment && (
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-surface px-5 py-[18px]">
              <div className="flex flex-col gap-1">
                <span className="text-[19px] font-medium tracking-[-0.02em]">
                  {formatLongDate(dateOf(appointment.start))} · {formatTime(appointment.start)}
                </span>
                <span className="text-[13.5px] text-ink-muted">
                  {doctor?.name ?? appointment.doctorId} · {minutes} min
                </span>
              </div>
              <span className="text-[13px] text-ink-muted">Arrive 10 minutes early</span>
            </div>
          )}
          <p className="text-[13.5px] leading-normal text-ink-muted">
            {busy
              ? "The clinic's AI service is at its free-tier limit right now. Please try again in a minute or two."
              : ended.summary}
          </p>
        </div>

        {filled.length > 0 && (
          <div className="flex flex-col px-6 pb-1.5 pt-3.5 max-sm:px-4">
            <h3 className="mb-1.5 text-[13px] font-semibold">Your details</h3>
            <dl>
              {filled.map(({ field, label }) => (
                <div key={field} className="flex justify-between gap-3 border-b border-surface-sunk py-[9px] text-[13.5px]">
                  <dt className="text-ink-faint">{label}</dt>
                  <dd className="text-right">{formatFormValue(field, form[field]?.value ?? "")}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        <div className="flex flex-wrap gap-2.5 px-3.5 pb-3.5 pt-2.5">
          <button
            type="button"
            onClick={onCallAgain}
            className="h-12 rounded-full bg-ink px-[26px] text-sm font-medium text-white transition-colors hover:bg-brand-hover"
          >
            Call again
          </button>
          <button type="button" onClick={() => void downloadTranscript()} className={secondaryButton}>
            Download transcript
          </button>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto h-12 px-4 text-sm font-medium text-ink-faint transition-colors hover:text-ink"
          >
            Back to desk
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
