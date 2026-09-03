"use client";

import { useEffect, useRef, useState } from "react";
import { animate, useInView } from "framer-motion";

import { PaperAirplane } from "@/components/paper-airplane";
import { Reveal } from "@/components/reveal";
import { fetchStats } from "@/lib/api";
import type { TrackRecordStats } from "@/lib/types";

function StatNumber({ value, decimals = 0, suffix = "" }: { value: number; decimals?: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (!inView) return;
    const controls = animate(0, value, {
      duration: 1.6,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => setDisplay(v),
    });
    return () => controls.stop();
  }, [inView, value]);

  return (
    <span ref={ref}>
      {display.toLocaleString(undefined, { maximumFractionDigits: decimals, minimumFractionDigits: decimals })}
      {suffix}
    </span>
  );
}

function StatCard({ label, value, decimals, suffix }: { label: string; value: number | null; decimals?: number; suffix?: string }) {
  return (
    <div>
      <p className="font-display text-6xl text-paper sm:text-7xl">
        {value === null ? <span className="text-paper/40">—</span> : <StatNumber value={value} decimals={decimals} suffix={suffix} />}
      </p>
      <p className="mt-3 text-sm text-paper/60">{label}</p>
    </div>
  );
}

export function TrackRecord() {
  const [stats, setStats] = useState<TrackRecordStats | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetchStats()
      .then(setStats)
      .catch(() => setFailed(true));
  }, []);

  return (
    <section id="track-record" className="relative border-t border-paper/10 bg-ink px-6 py-28">
      <PaperAirplane size={56} rotate={-10} className="absolute right-8 top-14 sm:right-16" bobDelay={0.6} />
      <div className="mx-auto max-w-5xl">
        <Reveal>
          <p className="mb-4 text-sm font-medium uppercase tracking-[0.2em] text-paper/50">Track record</p>
          <h2 className="font-display text-4xl leading-tight text-paper sm:text-5xl">
            Every forecast, checked against what actually happened.
          </h2>
          <p className="mt-4 max-w-xl text-lg text-paper/70">
            {failed
              ? "Couldn't reach the history store just now — these will populate once it's back."
              : "These numbers come straight from the persistent history store — not marketing copy. If nothing has run yet, they say so honestly."}
          </p>
        </Reveal>

        <Reveal delay={0.12} className="mt-16 grid grid-cols-2 gap-x-8 gap-y-12 sm:grid-cols-4">
          <StatCard label="Forecasts run" value={stats?.total_forecasts_run ?? null} />
          <StatCard label="Shortfalls flagged" value={stats?.shortfalls_flagged ?? null} />
          <StatCard label="Verified against real outcomes" value={stats?.verified_against_actuals ?? null} />
          <StatCard
            label="Directional accuracy on verified runs"
            value={stats?.directional_accuracy_pct ?? null}
            decimals={0}
            suffix="%"
          />
        </Reveal>
      </div>
    </section>
  );
}
