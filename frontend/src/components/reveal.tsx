"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

/** Shared scroll-triggered reveal: fade + slight upward slide as the
 * element enters the viewport, via a real IntersectionObserver (whileInView).
 * Deliberately understated -- no bounce, no overshoot -- per the brief. */
export function Reveal({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
