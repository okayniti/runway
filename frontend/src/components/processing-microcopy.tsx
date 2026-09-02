"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

// Dry, specific, and true to what the pipeline actually does at each
// stage -- not a generic "please wait" -- so it reads as a system telling
// you what it's doing, not decorative filler pretending to be busy.
const PHRASES = [
  "Reading the ledger.",
  "Aggregating daily cash positions.",
  "Weighing this window against its own history.",
  "Checking the horizon for a shortfall.",
  "Drafting recommendations, if any are warranted.",
];

const CYCLE_MS = 900;

/** Cycles through PHRASES on a fixed interval for as long as `active` is
 * true. The cycle itself is decorative timing (we don't know how long the
 * real request will take), but it's driven entirely by `active` -- it
 * stops the instant the caller's request resolves, not on a fixed
 * duration pretending to match the work. */
export function ProcessingMicrocopy({ active }: { active: boolean }) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (!active) {
      setIndex(0);
      return;
    }
    const id = setInterval(() => setIndex((i) => (i + 1) % PHRASES.length), CYCLE_MS);
    return () => clearInterval(id);
  }, [active]);

  if (!active) return null;

  return (
    <div className="flex items-center gap-2.5 text-sm text-ink-muted">
      <motion.span
        aria-hidden
        className="size-1.5 rounded-full bg-ember"
        animate={{ opacity: [0.3, 1, 0.3] }}
        transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
      />
      <AnimatePresence mode="wait">
        <motion.span
          key={index}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.25 }}
        >
          {PHRASES[index]}
        </motion.span>
      </AnimatePresence>
    </div>
  );
}
