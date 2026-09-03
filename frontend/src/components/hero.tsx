"use client";

import { motion } from "framer-motion";
import { ArrowDown } from "lucide-react";

import { PaperAirplane } from "@/components/paper-airplane";

// The old way runway replaces -- reinforces the headline rather than
// decorating around it. Deliberately understated (small, muted, tilted)
// so it never competes with the hero copy for attention.
const CHAOS_TAGS: { label: string; rotate: number }[] = [
  { label: "spreadsheet gut-checks", rotate: -3 },
  { label: "found out too late", rotate: 2 },
  { label: "manual reconciliation", rotate: -1.5 },
  { label: "chasing invoices", rotate: 3 },
  { label: "guessing the runway", rotate: -2 },
  { label: "Excel roulette", rotate: 1.5 },
  { label: "hoping payroll clears", rotate: -2.5 },
];

export function Hero() {
  return (
    <section id="top" className="relative flex min-h-screen flex-col justify-center px-6 pt-16 pb-20">
      {/* Grid texture lives on its own layer behind the content -- CSS
          mask-image affects an element's ENTIRE rendered output, children
          included, not just its background-image, so it can never be a
          class on the section that also holds the real content (that
          faded out the CTA button and tags along with the grid lines,
          exactly matching the radial mask's falloff -- caught by actually
          looking at a screenshot, not just checking for console errors). */}
      <div className="bg-grid pointer-events-none absolute inset-0" aria-hidden="true" />

      <PaperAirplane className="absolute right-6 top-28 sm:right-12 md:right-24" />

      <div className="mx-auto w-full max-w-5xl">
        <motion.p
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-6 text-sm font-medium uppercase tracking-[0.2em] text-ember"
        >
          Cash-flow forecasting, plainly stated
        </motion.p>

        <motion.h1
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.05 }}
          className="font-display text-[13vw] leading-[0.95] tracking-tight text-ink sm:text-[7.5rem] md:text-[8rem]"
        >
          See the shortfall
          <br />
          <span className="italic text-ember">before</span> it happens.
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="mt-8 max-w-xl text-lg text-ink-muted"
        >
          runway forecasts fourteen days ahead and tells you plainly when
          you&rsquo;re about to run short — with the specific line items and
          moves that would fix it.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.32 }}
          className="mt-10"
        >
          <a
            href="#forecast"
            className="inline-flex items-center gap-2 rounded-full bg-ember px-7 py-3.5 text-base font-medium text-paper transition-transform hover:scale-[1.03] active:scale-[0.98]"
          >
            Run a live forecast
            <ArrowDown className="size-4" />
          </a>
        </motion.div>

        <div className="mt-16">
          <p className="mb-4 text-xs font-medium uppercase tracking-[0.15em] text-ink-faint">The old way</p>
          <div className="flex max-w-2xl flex-wrap gap-3">
            {CHAOS_TAGS.map((tag, i) => (
              <motion.span
                key={tag.label}
                initial={{ opacity: 0, y: -70, rotate: 0 }}
                animate={{ opacity: 1, y: 0, rotate: tag.rotate }}
                transition={{
                  duration: 0.6,
                  delay: 0.6 + i * 0.07,
                  type: "spring",
                  stiffness: 140,
                  damping: 14,
                }}
                className="rounded-full border border-line bg-paper-card/70 px-3.5 py-1.5 text-xs text-ink-muted sm:text-sm"
              >
                {tag.label}
              </motion.span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
