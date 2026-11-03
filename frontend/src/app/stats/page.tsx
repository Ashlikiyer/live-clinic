import type { Metadata } from "next";

import { StatsDashboard } from "@/components/stats/StatsDashboard";

export const metadata: Metadata = {
  title: "Latency stats · Live Clinic Desk",
  description: "How fast Mia replies: reply time by pipeline stage over the last 7 days.",
};

export default function StatsPage() {
  return <StatsDashboard />;
}
