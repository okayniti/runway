"use client";

import { motion } from "framer-motion";
import { ArrowDown } from "lucide-react";

export function Hero() {
  return (
    <section id="top" className="relative flex min-h-screen flex-col justify-center px-6 pt-16">
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
      </div>
    </section>
  );
}
