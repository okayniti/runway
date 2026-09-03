"use client";

import { motion } from "framer-motion";

/** A seeded pseudo-random in [0, 1), pure in `seed` -- unlike Math.random()
 * this gives the same fall/tumble values on the server render and the
 * client render (no hydration mismatch) and satisfies the rule against
 * calling impure functions during render (an inline Math.random() inside
 * useMemo still runs at render time and tripped exactly that lint rule). */
function seededRandom(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

// The old way runway replaces. A wider, deliberately colorful accent set
// used ONLY here -- distinct from the two-color ember/moss system that
// carries actual meaning (risk/safe) everywhere else on the site, so this
// decorative moment doesn't dilute that semantic. All seven are original,
// muted/dusty hues (no bright primaries, no SaaS blue) picked for enough
// contrast against the light "text-paper" label on top.
const CHAOS_TAGS: { label: string; color: string }[] = [
  { label: "spreadsheet gut-checks", color: "#b5482a" }, // ember (terracotta)
  { label: "found out too late", color: "#4b6455" }, // moss (sage)
  { label: "manual reconciliation", color: "#96591b" }, // burnt amber
  { label: "chasing invoices", color: "#6b3f52" }, // dusty plum
  { label: "guessing the runway", color: "#3f5468" }, // dusty indigo-slate
  { label: "Excel roulette", color: "#2a241c" }, // ink
  { label: "hoping payroll clears", color: "#8c5a3c" }, // warm clay
];

/** Tags drop in from above, tumbling and drifting like they're falling
 * under gravity, then bounce-settle into place via a spring. The settled
 * layout itself is a plain CSS flex-wrap, so "untangled" (zero overlap) is
 * a hard guarantee from the browser's own layout engine rather than
 * something hand-tuned out of a physics solver.
 *
 * A real rigid-body engine (Matter.js) was tried first. Even with a wide
 * drop area, well above the Matter.js defaults on solver iteration count,
 * and multiple rounds of inertia/chamfer tuning, seven pills this close in
 * size kept either interpenetrating under solver pressure or flipping onto
 * an edge under collision torque -- and fixing one made the other worse
 * (heavier inertia to stop the edge-flip left bodies too rotationally
 * stiff to rotate the small amount needed to slot into a gap, which made
 * overlap markedly worse, confirmed by a pairwise bounding-box check
 * before this rewrite). Flex-wrap sidesteps the collision problem
 * entirely and, with a spring per tag, still reads as a physical fall. */
export function ChaosTags() {
  const motionProps = CHAOS_TAGS.map((_, i) => ({
    startRotate: (i % 2 === 0 ? 1 : -1) * (110 + seededRandom(i * 3) * 90),
    endRotate: (seededRandom(i * 3 + 1) - 0.5) * 6,
    startX: (seededRandom(i * 3 + 2) - 0.5) * 60,
    startY: -260 - i * 22,
    delay: 0.5 + i * 0.09,
  }));

  return (
    // gap-y is generous, not just for visual spacing: getBoundingClientRect
    // measures each pill's rotated (axis-aligned) footprint, and flex-wrap
    // only guarantees clearance between the UNROTATED boxes -- a several-
    // degree settled tilt on a wide pill was enough to push its rotated
    // corners into a 12px row gap and register as real overlap on a
    // pairwise bounding-box check, even though nothing looked wrong at a
    // glance. This gap comfortably clears that at the capped tilt below.
    <div className="flex max-w-3xl flex-wrap gap-x-3 gap-y-8">
      {CHAOS_TAGS.map((tag, i) => {
        const m = motionProps[i];
        return (
          <motion.span
            key={tag.label}
            initial={{ y: m.startY, x: m.startX, rotate: m.startRotate, opacity: 0 }}
            animate={{ y: 0, x: 0, rotate: m.endRotate, opacity: 1 }}
            transition={{
              y: { type: "spring", damping: 12, stiffness: 95, mass: 1, delay: m.delay },
              x: { type: "spring", damping: 14, stiffness: 90, mass: 1, delay: m.delay },
              rotate: { type: "spring", damping: 10, stiffness: 80, mass: 1, delay: m.delay },
              opacity: { duration: 0.2, delay: m.delay },
            }}
            className="whitespace-nowrap rounded-full px-3.5 py-1.5 text-xs font-medium text-paper sm:text-sm"
            style={{ backgroundColor: tag.color }}
          >
            {tag.label}
          </motion.span>
        );
      })}
    </div>
  );
}
