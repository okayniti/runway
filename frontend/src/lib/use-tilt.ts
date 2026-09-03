"use client";

import { useRef, type MouseEvent } from "react";
import { useMotionValue, useSpring, useTransform } from "framer-motion";

const TILT_RANGE = 8; // degrees, each direction

/** The cursor-follow feel from photos on the reference site, applied to
 * our bento cards instead (we have no photos) -- a subtle 3D tilt toward
 * the pointer, sprung back to flat on mouse-leave. Returns props to spread
 * directly onto a motion.div; composes cleanly with that div's own
 * variants/whileHover since rotateX/rotateY are independent of the
 * opacity/y/scale transforms those already handle. */
export function useTilt() {
  const ref = useRef<HTMLDivElement>(null);
  const px = useMotionValue(0.5);
  const py = useMotionValue(0.5);

  const rotateX = useSpring(useTransform(py, [0, 1], [TILT_RANGE, -TILT_RANGE]), {
    stiffness: 300,
    damping: 22,
  });
  const rotateY = useSpring(useTransform(px, [0, 1], [-TILT_RANGE, TILT_RANGE]), {
    stiffness: 300,
    damping: 22,
  });

  function onMouseMove(e: MouseEvent<HTMLDivElement>) {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    px.set((e.clientX - rect.left) / rect.width);
    py.set((e.clientY - rect.top) / rect.height);
  }

  function onMouseLeave() {
    px.set(0.5);
    py.set(0.5);
  }

  return { ref, style: { rotateX, rotateY, transformPerspective: 800 }, onMouseMove, onMouseLeave };
}
