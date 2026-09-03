"use client";

import { useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";

/** Two keyframes of the same wave path, differing only in how far each
 * control point sits from the shared y=55 midline -- i.e. the wave's
 * amplitude, not its position. Both share identical path structure (same
 * M/C/L/Z commands, same point count), which is what lets framer-motion
 * morph smoothly between them via useTransform rather than hard-cutting
 * from one shape to another.
 *
 * COMPRESSED (entering/leaving): M0,59.25 C240,21 480,89 720,55 C960,21
 * 1200,89 1440,50.75. STRETCHED (centered in view): M0,60.5 C240,11
 * 480,99 720,55 C960,11 1200,99 1440,49.5. A 29% swing in the path's own
 * amplitude -- more than double the original ~13% -- combined with the
 * scaleY layered on top in the component below for a genuinely elastic
 * feel, while y3's stretched value (99) still stays under the viewBox's
 * own 100-unit height so the path itself never clips. */
const WAVE_COMPRESSED = "M0,59.25 C240,21 480,89 720,55 C960,21 1200,89 1440,50.75 L1440,100 L0,100 Z";
const WAVE_STRETCHED = "M0,60.5 C240,11 480,99 720,55 C960,11 1200,99 1440,49.5 L1440,100 L0,100 Z";

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
 * site's rendering is unchanged.
 *
 * Two effects are scroll-linked, not static, both driven by the same
 * scrollYProgress (0 = top of this element hits the bottom of the
 * viewport, 1 = its bottom leaves the top), compressed/1x while
 * entering and leaving, stretched/`maxScaleY` while centered:
 * 1. the path's own amplitude, morphing between the two keyframe strings
 *    above (a genuine shape change, not just a scale) -- always safe,
 *    never overflows the viewBox regardless of `maxScaleY`.
 * 2. a CSS scaleY on top of that, anchored to the top edge
 *    (transformOrigin: "top") so growth reads as the wave's dip
 *    reaching further DOWN into the section it's easing into, not
 *    stretching symmetrically off both edges. `overflow-visible` on the
 *    svg lets that extra height actually show at the peak instead of
 *    being clipped by the wrapping div's own fixed h-16/h-24.
 *
 * `maxScaleY` (default 1.35, a pronounced elastic stretch) needs a
 * seam-by-seam check, not a global assumption: verified visually at both
 * default-sized seams (FeaturesGrid/CalibrationSpotlight, py-28 and
 * pt-16 padding either side) with 60-100px of clearance to the nearest
 * real content at peak stretch -- fine. NOT fine, also found the same
 * way, at the capability-marquee seam: that section's py-6 is nowhere
 * near enough clearance, and at 1.35 the peak visibly cut through the
 * marquee's own airplane and pill row. That call site passes a lower
 * override instead of the whole component quietly using a smaller
 * default everywhere (which would mean the two roomier seams stretch
 * less than they safely could). */
export function SectionWave({
  fill = "var(--color-ink)",
  behindFill = "var(--color-paper)",
  maxScaleY = 1.35,
}: {
  fill?: string;
  behindFill?: string;
  maxScaleY?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const d = useTransform(scrollYProgress, [0, 0.5, 1], [WAVE_COMPRESSED, WAVE_STRETCHED, WAVE_COMPRESSED]);
  const scaleY = useTransform(scrollYProgress, [0, 0.5, 1], [1, maxScaleY, 1]);

  return (
    <div ref={ref} className="h-16 w-full sm:h-24" style={{ backgroundColor: behindFill }} aria-hidden="true">
      <motion.svg
        viewBox="0 0 1440 100"
        preserveAspectRatio="none"
        className="h-full w-full overflow-visible"
        style={{ scaleY, transformOrigin: "top" }}
      >
        <motion.path d={d} fill={fill} />
      </motion.svg>
    </div>
  );
}
