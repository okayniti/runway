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

/** A wave divider at a section seam. The path's filled region is always
 * the BOTTOM of its own container (the curve down to the container's
 * bottom edge), so `fill` -- the color of the section that follows --
 * always meets that next section seamlessly. The region ABOVE the curve
 * is transparent, which only reads correctly if whatever's directly
 * behind the wrapping div matches the PRECEDING section: for the
 * original placement (preceding section paper-dim) that happened for
 * free, since paper-dim sits only 1.13:1 off the page's own default
 * paper background -- effectively invisible. It does NOT happen for
 * free when the preceding section is ink (11-13:1 off paper, nowhere
 * close) -- without `behindFill` set explicitly there, the transparent
 * area would show the page's light default right under a dark section,
 * a visible seam of its own. `behindFill` makes that previously-implicit
 * assumption an explicit, correct parameter instead of a coincidence,
 * defaulting to the page's own paper background so the original call
 * site's rendering is unchanged. */
export function SectionWave({
  fill = "var(--color-ink)",
  behindFill = "var(--color-paper)",
}: {
  fill?: string;
  behindFill?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const d = useTransform(scrollYProgress, [0, 0.5, 1], [WAVE_COMPRESSED, WAVE_STRETCHED, WAVE_COMPRESSED]);

  return (
    <div ref={ref} className="h-16 w-full sm:h-24" style={{ backgroundColor: behindFill }} aria-hidden="true">
      <svg viewBox="0 0 1440 100" preserveAspectRatio="none" className="h-full w-full">
        <motion.path d={d} fill={fill} />
      </svg>
    </div>
  );
}
