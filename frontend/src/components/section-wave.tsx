"use client";

import { useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";

/** Three keyframes of the same wave path, differing only in how far each
 * control point sits from the shared y=55 midline -- i.e. the wave's
 * amplitude, not its position. All three share identical path structure
 * (same M/C/L/Z commands, same point count), which is what lets
 * framer-motion morph smoothly between them via useTransform rather than
 * hard-cutting from one shape to another.
 *
 * COMPRESSED (k=0.95, entering/leaving): amplitude scaled to 95% of
 * baseline -- M0,59.75 C240,17 480,93 720,55 C960,17 1200,93 1440,50.25.
 * STRETCHED (k=1.08, centered in view): amplitude scaled to 108% --
 * M0,60.4 C240,11.8 480,98.2 720,55 C960,11.8 1200,98.2 1440,49.6.
 * Deliberately narrow (13% swing peak-to-peak, well inside the 0-100
 * viewBox so nothing clips) -- "alive," not distracting, per spec. */
const WAVE_COMPRESSED = "M0,59.75 C240,17 480,93 720,55 C960,17 1200,93 1440,50.25 L1440,100 L0,100 Z";
const WAVE_STRETCHED = "M0,60.4 C240,11.8 480,98.2 720,55 C960,11.8 1200,98.2 1440,49.6 L1440,100 L0,100 Z";

/** A wave divider at a light-to-dark seam. The SVG background is
 * transparent above the wave path (so whatever section sits behind shows
 * through) and the path itself is filled with the color of the section
 * that follows -- placed flush against that section, the wave reads as
 * the top edge dipping down into it rather than a separate decorative
 * strip.
 *
 * The path's amplitude is scroll-linked, not static: compressed while
 * entering and leaving the viewport, subtly stretched while centered in
 * it, via useScroll's scrollYProgress (0 = top of this element hits the
 * bottom of the viewport, 1 = its bottom leaves the top) mapped through
 * useTransform onto the two keyframe path strings above. */
export function SectionWave({ fill = "var(--color-ink)" }: { fill?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const d = useTransform(scrollYProgress, [0, 0.5, 1], [WAVE_COMPRESSED, WAVE_STRETCHED, WAVE_COMPRESSED]);

  return (
    <div ref={ref} className="h-16 w-full sm:h-24" aria-hidden="true">
      <svg viewBox="0 0 1440 100" preserveAspectRatio="none" className="h-full w-full">
        <motion.path d={d} fill={fill} />
      </svg>
    </div>
  );
}
