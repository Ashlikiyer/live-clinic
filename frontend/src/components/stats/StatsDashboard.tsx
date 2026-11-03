"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { API_URL } from "@/lib/api";
import type { StatsResponse } from "@/lib/statsView";
import { formatMs } from "@/lib/time";

import { DailyChart } from "./DailyChart";
import { Histogram } from "./Histogram";
import { SlowCauses } from "./SlowCauses";
import { StageBreakdown } from "./StageBreakdown";

type Load = { state: "loading" } | { state: "error" } | { state: "ready"; data: StatsResponse };

export function StatsDashboard() {
  const [load, setLoad] = useState<Load>({ state: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/api/stats`, { signal: controller.signal })
      .then((r) => (r.ok ? (r.json() as Promise<StatsResponse>) : Promise.reject(new Error("bad status"))))
      .then((data) => setLoad({ state: "ready", data }))
      .catch(() => {
        if (!controller.signal.aborted) setLoad({ state: "error" });
      });
    return () => controller.abort();
  }, []);

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm text-ink-muted">Live Clinic Desk</p>
          <h1 className="text-2xl font-semibold tracking-tight">How fast Mia replies</h1>
          <p className="mt-1 max-w-2xl text-sm text-ink-muted">
            Time from the end of a caller&apos;s speech to Mia&apos;s first audio, across every demo
            call in the last 7 days. Aggregates only: no transcripts or caller details.
          </p>
        </div>
        <Link href="/" className="rounded-full border border-line px-4 py-2 text-sm hover:bg-surface-muted">
          Call the clinic
        </Link>
      </header>

      {load.state === "loading" && <p className="text-sm text-ink-muted">Loading stats... (the backend may take a minute to wake up)</p>}
      {load.state === "error" && <p className="text-sm text-ink-muted">Stats are unavailable right now. Please try again in a minute.</p>}
      {load.state === "ready" && load.data.replies === 0 && (
        <p className="rounded-2xl border border-line bg-surface p-6 text-sm text-ink-muted">
          No measured replies in the last 7 days yet. Make a call, then come back.
        </p>
      )}
      {load.state === "ready" && load.data.replies > 0 && <Dashboard data={load.data} />}
    </main>
  );
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-line bg-surface p-4 sm:p-5">
      <h2 className="font-semibold">{title}</h2>
      {subtitle && <p className="mt-0.5 text-sm text-ink-muted">{subtitle}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="mt-0.5 text-xl font-semibold">{value}</p>
      {note && <p className="text-[11px] text-ink-muted">{note}</p>}
    </div>
  );
}

function Dashboard({ data }: { data: StatsResponse }) {
  const ms = (v: number | null) => (v === null ? "—" : formatMs(v));
  const slowPct = data.slow_turn_share === null ? "—" : `${Math.round(data.slow_turn_share * 100)}%`;
  return (
    <div className="space-y-4">
      <section className="flex flex-wrap items-end gap-x-8 gap-y-4 rounded-2xl border border-line bg-surface p-5">
        <div>
          <p className="text-sm text-ink-muted">Median reply time</p>
          <p className="text-5xl font-semibold tracking-tight">{ms(data.median_total_ms)}</p>
          <p className="mt-1 text-xs text-ink-muted">target 1.5 s</p>
        </div>
        <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-5">
          <Tile label="p95 reply time" value={ms(data.p95_total_ms)} />
          <Tile label="Replies" value={data.replies.toLocaleString()} />
          <Tile label="Calls" value={data.calls.toLocaleString()} />
          <Tile label="Slower than 2 s" value={slowPct} />
          <Tile
            label="Interruptions"
            value={data.interruptions.toLocaleString()}
            note={data.avg_stop_ms === null ? undefined : `silent ${ms(data.avg_stop_ms)} after caller speaks`}
          />
        </div>
      </section>

      <Card title="Where a typical reply's time goes" subtitle="Median of each pipeline stage">
        <StageBreakdown medians={data.stage_medians} />
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Reply time distribution" subtitle="Replies per 250 ms, all calls">
          <Histogram hist={data.total_ms_histogram} />
        </Card>
        <Card title="Last 7 days" subtitle="Daily median and p95 reply time">
          <DailyChart daily={data.daily} />
        </Card>
      </div>

      <Card
        title="What made slow replies slow"
        subtitle={`Replies over ${formatMs(data.slow_turn_threshold_ms)}, by their slowest stage`}
      >
        <SlowCauses causes={data.slow_turn_causes} />
      </Card>
    </div>
  );
}
