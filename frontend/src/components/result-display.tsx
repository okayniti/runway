"use client";

import { motion } from "framer-motion";
import {
  AlertTriangle,
  Building2,
  CalendarClock,
  CheckCircle2,
  CircleDollarSign,
  Receipt,
  TrendingUp,
  Users,
  Zap,
  type LucideIcon,
} from "lucide-react";

import { ForecastChart } from "@/components/forecast-chart";
import type { ContributingLineItem, ForecastOutput, Recommendation } from "@/lib/types";

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  payroll: Users,
  rent: Building2,
  payable: Receipt,
  receivable: TrendingUp,
};

const ACTION_ICONS: Record<Recommendation["action"], LucideIcon> = {
  delay_payment: CalendarClock,
  accelerate_collection: Zap,
};

const listStagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
};

const cardReveal = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45 } },
};

function LineItemCard({ item }: { item: ContributingLineItem }) {
  const Icon = CATEGORY_ICONS[item.category] ?? CircleDollarSign;
  return (
    <motion.div
      variants={cardReveal}
      whileHover={{ y: -3 }}
      className="rounded-2xl border border-line bg-paper-card p-5 transition-shadow hover:shadow-md"
    >
      <div className="mb-3 flex items-center justify-between">
        <span className="flex size-9 items-center justify-center rounded-full bg-ember-dim text-ember">
          <Icon className="size-4.5" strokeWidth={1.75} />
        </span>
        <span className="text-xs text-ink-faint">{item.date}</span>
      </div>
      <p className="font-display text-2xl text-ink">
        {item.amount.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 })}
      </p>
      <p className="mt-1 text-sm text-ink-muted capitalize">{item.category}</p>
      <p className="mt-2 text-xs text-ink-faint">
        {item.basis === "recurring_projection" ? "Projected from recurring pattern" : "Recent outlier in your history"}
      </p>
    </motion.div>
  );
}

function RecommendationCard({ rec }: { rec: Recommendation }) {
  const Icon = ACTION_ICONS[rec.action];
  return (
    <motion.div
      variants={cardReveal}
      whileHover={{ y: -3 }}
      className="rounded-2xl border border-line bg-paper-card p-5 transition-shadow hover:shadow-md"
    >
      <div className="mb-3 flex items-center gap-2">
        <span className="flex size-9 items-center justify-center rounded-full bg-moss-dim text-moss">
          <Icon className="size-4.5" strokeWidth={1.75} />
        </span>
        <span className="text-xs font-medium uppercase tracking-wide text-moss">Rank {rec.rank}</span>
      </div>
      <p className="text-sm leading-relaxed text-ink">{rec.description}</p>
      <p className="mt-3 text-sm font-medium text-ink">
        +
        {rec.projected_shortfall_relief.toLocaleString(undefined, {
          style: "currency",
          currency: "USD",
          maximumFractionDigits: 0,
        })}{" "}
        <span className="font-normal text-ink-muted">projected relief</span>
      </p>
    </motion.div>
  );
}

export function ResultDisplay({ result, threshold }: { result: ForecastOutput; threshold: number }) {
  const { risk_flag, risk_reason, forecast, confidence, contributing_line_items, recommendations } = result;

  return (
    <motion.div initial="hidden" animate="show" variants={listStagger} className="mt-8 space-y-6">
      {/* Risk banner — calm, plain-language, colored by state */}
      <motion.div
        variants={cardReveal}
        className={`flex items-start gap-3 rounded-2xl border p-5 ${
          risk_flag ? "border-ember/30 bg-ember-dim text-ember" : "border-moss/30 bg-moss-dim text-moss"
        }`}
      >
        {risk_flag ? (
          <AlertTriangle className="mt-0.5 size-5 shrink-0" strokeWidth={1.75} />
        ) : (
          <CheckCircle2 className="mt-0.5 size-5 shrink-0" strokeWidth={1.75} />
        )}
        <p className="text-sm leading-relaxed">
          {risk_flag ? risk_reason : "No shortfall risk detected for this forecast window."}
        </p>
      </motion.div>

      {/* Chart — the visual centerpiece */}
      <motion.div variants={cardReveal} className="rounded-3xl border border-line bg-paper-card p-6 sm:p-10">
        <div className="mb-6 flex items-baseline justify-between">
          <h3 className="font-display text-2xl text-ink">14-day forecast</h3>
          <span className="text-sm text-ink-muted">
            Confidence {confidence.score.toFixed(2)} · {confidence.is_low_confidence ? "low" : "adequate"}
          </span>
        </div>
        <ForecastChart forecast={forecast} threshold={threshold} atRisk={risk_flag} />
        {confidence.reasons.length > 0 && (
          <ul className="mt-4 space-y-1 text-xs text-ink-faint">
            {confidence.reasons.map((reason) => (
              <li key={reason}>— {reason}</li>
            ))}
          </ul>
        )}
      </motion.div>

      {/* Contributing line items — bento grid */}
      {contributing_line_items.length > 0 && (
        <motion.div variants={cardReveal}>
          <h3 className="mb-4 font-display text-2xl text-ink">What&rsquo;s driving it</h3>
          <motion.div
            variants={listStagger}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.2 }}
            className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
          >
            {contributing_line_items.map((item, i) => (
              <LineItemCard key={`${item.date}-${item.category}-${i}`} item={item} />
            ))}
          </motion.div>
        </motion.div>
      )}

      {/* Recommendations — bento grid */}
      {recommendations.length > 0 && (
        <motion.div variants={cardReveal}>
          <h3 className="mb-4 font-display text-2xl text-ink">What would fix it</h3>
          <motion.div
            variants={listStagger}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.2 }}
            className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
          >
            {recommendations.map((rec) => (
              <RecommendationCard key={rec.rank} rec={rec} />
            ))}
          </motion.div>
        </motion.div>
      )}
    </motion.div>
  );
}
