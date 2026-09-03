"use client";

import dynamic from "next/dynamic";
import { motion } from "framer-motion";
import { ArrowDown } from "lucide-react";

import { PaperAirplane } from "@/components/paper-airplane";

// Client-only. The fall values are deterministic (no Math.random() at
// render time), but framer-motion still serializes its inline transform/
// opacity styles with different float precision and unit formatting
// between the server render and the client mount ("0" vs 0, rounded vs
// full-precision translateX) -- a known framer-motion + Next SSR quirk,
// confirmed by re-checking the console after switching to seeded values:
// the mismatch persisted with identical numbers on both sides, just
// formatted differently. Skipping SSR for this purely decorative block
// sidesteps it outright.
const ChaosTags = dynamic(() => import("@/components/chaos-tags").then((m) => m.ChaosTags), { ssr: false });

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

      <PaperAirplane edgeOffset="tight" className="absolute top-28" />

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
          <ChaosTags />
        </div>
      </div>
    </section>
  );
}
