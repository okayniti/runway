"use client";

import { motion, type Variants } from "framer-motion";
import { BellRing, Database, KeySquare, ListChecks, type LucideIcon } from "lucide-react";

import { PaperAirplane } from "@/components/paper-airplane";
import { Reveal } from "@/components/reveal";

const FEATURES: { icon: LucideIcon; title: string; description: string }[] = [
  {
    icon: ListChecks,
    title: "Not just a warning — a plan.",
    description:
      "When you're at risk, runway proposes ranked, dollar-specific moves — delay this payment, accelerate that collection — computed from your real ledger, never freeform.",
  },
  {
    icon: BellRing,
    title: "A tool you don't have to remember to open.",
    description:
      "An optional scheduler re-runs the forecast on its own and pings a webhook the moment risk flips true, before you'd have thought to check.",
  },
  {
    icon: KeySquare,
    title: "Built for more than one business.",
    description:
      "Every request is scoped by an API key to its own tenant — its own history, its own track record — even when you're only running one.",
  },
  {
    icon: Database,
    title: "Nothing evaporates after the response.",
    description:
      "Every forecast is logged, and once real time catches up to its horizon, checked against what actually happened — automatically.",
  },
];

// Typed explicitly as Variants -- without it, TS infers `ease`'s cubic-
// bezier tuple as a generic number[] here (this object has no contextual
// type to narrow against, unlike an inline `transition={{ ease: [...] }}`
// prop elsewhere in this codebase, where the JSX prop's own expected type
// does that narrowing for free), which mismatches framer-motion's actual
// Easing type and fails `next build`'s type-check outright -- caught by
// running a real production build, not just `tsc --noEmit` in isolation.
const gridStagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.1 } },
};

const cardReveal: Variants = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } },
};

export function FeaturesGrid() {
  return (
    <section className="relative bg-paper-dim px-6 py-28">
      <PaperAirplane size={56} rotate={-18} side="left" className="absolute top-14" bobDelay={0.6} />
      <div className="mx-auto max-w-5xl">
        <Reveal>
          <p className="mb-4 text-sm font-medium uppercase tracking-[0.2em] text-ember">Beyond the forecast</p>
          <h2 className="font-display text-4xl leading-tight text-ink sm:text-5xl">
            The agent layer, not just the model.
          </h2>
        </Reveal>

        <motion.div
          variants={gridStagger}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.2 }}
          className="mt-14 grid grid-cols-1 gap-6 sm:grid-cols-2"
        >
          {FEATURES.map(({ icon: Icon, title, description }) => (
            <motion.div
              key={title}
              variants={cardReveal}
              whileHover={{ y: -4 }}
              className="rounded-3xl border border-line bg-paper-card p-8 transition-shadow hover:shadow-md"
            >
              <span className="mb-5 flex size-11 items-center justify-center rounded-full bg-ember-dim text-ember">
                <Icon className="size-5" strokeWidth={1.75} />
              </span>
              <h3 className="font-display text-xl text-ink">{title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-ink-muted">{description}</p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
