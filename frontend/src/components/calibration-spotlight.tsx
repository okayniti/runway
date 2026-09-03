"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ShieldCheck } from "lucide-react";

import { PaperAirplane } from "@/components/paper-airplane";
import { Reveal } from "@/components/reveal";
import { fetchCalibration } from "@/lib/api";
import type { CalibrationReport } from "@/lib/types";

const TAGS = ["Backfilled automatically", "Bucketed by confidence", "No fabricated verdicts"];

const BUCKET_LABELS: Record<string, string> = {
  low_confidence: "Low-confidence runs",
  high_confidence: "High-confidence runs",
};

function BucketBar({ label, runs, meanRmse, maxRuns, color }: { label: string; runs: number; meanRmse: number | null; maxRuns: number; color: "ember" | "moss" }) {
  const widthPct = maxRuns > 0 ? Math.max((runs / maxRuns) * 100, runs > 0 ? 6 : 0) : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm text-paper/70">
        <span>{label}</span>
        <span>
          {runs} run{runs === 1 ? "" : "s"}
          {meanRmse != null ? ` · ${meanRmse.toLocaleString(undefined, { maximumFractionDigits: 0 })} avg RMSE` : ""}
        </span>
      </div>
      <div className="mt-2 h-3 w-full overflow-hidden rounded-full bg-paper/10">
        <motion.div
          initial={{ width: 0 }}
          whileInView={{ width: `${widthPct}%` }}
          viewport={{ once: true, amount: 0.6 }}
          transition={{ duration: 0.9, ease: "easeOut" }}
          className={`h-full rounded-full ${color === "ember" ? "bg-ember" : "bg-moss"}`}
        />
      </div>
    </div>
  );
}

export function CalibrationSpotlight() {
  const [report, setReport] = useState<CalibrationReport | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetchCalibration()
      .then(setReport)
      .catch(() => setFailed(true));
  }, []);

  const low = report?.buckets.find((b) => b.label === "low_confidence");
  const high = report?.buckets.find((b) => b.label === "high_confidence");
  const maxRuns = Math.max(low?.num_runs ?? 0, high?.num_runs ?? 0);

  return (
    <section className="relative bg-ink px-6 pt-16 pb-28">
      <PaperAirplane size={56} rotate={14} flip className="absolute top-24" bobDelay={0.6} />
      <div className="mx-auto max-w-5xl">
        <Reveal>
          <span className="inline-flex items-center gap-2 rounded-full border border-paper/20 px-3.5 py-1.5 text-xs font-medium uppercase tracking-wide text-paper/70">
            <ShieldCheck className="size-3.5" strokeWidth={1.75} />
            Real finding, not marketing copy
          </span>
          <h2 className="mt-6 max-w-3xl font-display text-4xl leading-tight text-paper sm:text-5xl">
            We&rsquo;d rather say &ldquo;not enough evidence yet&rdquo; than fake a verdict.
          </h2>
          <p className="mt-4 max-w-2xl text-lg text-paper/70">
            {failed
              ? "Couldn't reach the history store just now for this one."
              : report && report.total_runs_with_known_outcome > 0
                ? report.summary
                : "No logged run has a known outcome yet — this fills in as forecasts get verified against reality."}
          </p>
        </Reveal>

        <Reveal delay={0.12} className="mt-14 grid gap-10 sm:grid-cols-[1fr_auto] sm:items-start">
          <div className="space-y-6">
            <BucketBar
              label={BUCKET_LABELS.low_confidence}
              runs={low?.num_runs ?? 0}
              meanRmse={low?.mean_error_rmse ?? null}
              maxRuns={maxRuns}
              color="ember"
            />
            <BucketBar
              label={BUCKET_LABELS.high_confidence}
              runs={high?.num_runs ?? 0}
              meanRmse={high?.mean_error_rmse ?? null}
              maxRuns={maxRuns}
              color="moss"
            />
          </div>

          <div className="flex flex-wrap gap-2 sm:flex-col sm:items-end">
            {TAGS.map((tag) => (
              <span
                key={tag}
                className="whitespace-nowrap rounded-full border border-paper/20 px-3.5 py-1.5 text-xs text-paper/70"
              >
                {tag}
              </span>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}
