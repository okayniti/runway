"use client";

import { motion } from "framer-motion";

/** The site's one decorative character -- a folded-paper airplane, tying
 * directly to "runway" rather than an arbitrary mascot. Two-layer motion:
 * the outer wrapper does a one-time entrance (fade/scale/rotate into
 * position), the inner svg then idles with a continuous gentle bank once
 * that settles, so it never fights the section's own copy for attention.
 * One placed per section, each with its own size/rotation/flip/timing so
 * they read as a recurring motif rather than one sticker copy-pasted
 * everywhere. */
export function PaperAirplane({
  className = "",
  size = 72,
  rotate = -12,
  flip = false,
  entranceDelay = 0.55,
  bobDelay = 1.2,
}: {
  className?: string;
  size?: number;
  rotate?: number;
  flip?: boolean;
  entranceDelay?: number;
  bobDelay?: number;
}) {
  return (
    <motion.div
      aria-hidden="true"
      className={`pointer-events-none select-none ${className}`}
      style={flip ? { scaleX: -1 } : undefined}
      initial={{ opacity: 0, scale: 0.6, rotate: rotate - 23 }}
      animate={{ opacity: 1, scale: 1, rotate }}
      transition={{ duration: 0.7, delay: entranceDelay, ease: [0.22, 1, 0.36, 1] }}
    >
      <motion.svg
        width={size}
        height={size}
        viewBox="0 0 100 100"
        fill="none"
        animate={{ y: [0, -14, 0], rotate: [0, 7, 0] }}
        transition={{ duration: 5, repeat: Infinity, ease: "easeInOut", delay: bobDelay }}
      >
        <polygon points="50,8 8,88 50,64" fill="var(--color-ember)" />
        <polygon points="50,8 92,88 50,64" fill="var(--color-ember)" opacity="0.55" />
        <line x1="50" y1="8" x2="50" y2="64" stroke="var(--color-paper)" strokeWidth="1.5" opacity="0.45" />
      </motion.svg>
    </motion.div>
  );
}
