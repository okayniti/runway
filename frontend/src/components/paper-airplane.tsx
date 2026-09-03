"use client";

import { motion } from "framer-motion";

/** Every instance's near-edge offset, as a matched left/right pair of
 * literal Tailwind class strings. Both branches have to be spelled out in
 * full here (not built with template-string concatenation from a number
 * prop) -- Tailwind's build-time scanner only generates CSS for class
 * names it can find as literal text in a source file, so a runtime
 * `right-${n}` would silently produce no styling at all. Three shapes
 * cover every current call site: "wide" is the shared shape five of the
 * seven sections already used (right-8 sm:right-16), "tight" is the
 * hero's own three-tier shape, "marquee" is the one section with no
 * responsive variant at all. */
const EDGE_OFFSETS = {
  wide: { left: "left-8 sm:left-16", right: "right-8 sm:right-16" },
  tight: { left: "left-6 sm:left-12 md:left-24", right: "right-6 sm:right-12 md:right-24" },
  marquee: { left: "left-6", right: "right-6" },
} as const;

/** The site's one decorative character -- a folded-paper airplane, tying
 * directly to "runway" rather than an arbitrary mascot. Two-layer motion:
 * the outer wrapper does a one-time entrance (fade/scale/rotate into
 * position), the inner svg then idles with a continuous gentle bank once
 * that settles, so it never fights the section's own copy for attention.
 * One placed per section, each with its own size/rotation/flip/timing so
 * they read as a recurring motif rather than one sticker copy-pasted
 * everywhere.
 *
 * `side` picks which edge it's anchored to -- callers alternate this down
 * the page so the mascot doesn't sit right-aligned in every section (see
 * each call site). `className` carries everything else about its
 * position (top offset, z-index, translate) exactly as before; only the
 * horizontal edge classes moved out of it and into `side`/`edgeOffset`. */
export function PaperAirplane({
  className = "",
  size = 72,
  rotate = -12,
  flip = false,
  entranceDelay = 0.55,
  bobDelay = 1.2,
  side = "right",
  edgeOffset = "wide",
}: {
  className?: string;
  size?: number;
  rotate?: number;
  flip?: boolean;
  entranceDelay?: number;
  bobDelay?: number;
  side?: "left" | "right";
  edgeOffset?: keyof typeof EDGE_OFFSETS;
}) {
  const edgeClassName = EDGE_OFFSETS[edgeOffset][side];
  return (
    <motion.div
      aria-hidden="true"
      className={`pointer-events-none select-none ${edgeClassName} ${className}`}
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
