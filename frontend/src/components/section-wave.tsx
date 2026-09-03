/** A wave divider at a light-to-dark seam. The SVG background is
 * transparent above the wave path (so whatever section sits behind shows
 * through) and the path itself is filled with the color of the section
 * that follows -- placed flush against that section, the wave reads as
 * the top edge dipping down into it rather than a separate decorative
 * strip. Used once, at the single starkest light/dark seam on the page,
 * not at every section boundary. */
export function SectionWave({ fill = "var(--color-ink)" }: { fill?: string }) {
  return (
    <div className="h-16 w-full sm:h-24" aria-hidden="true">
      <svg viewBox="0 0 1440 100" preserveAspectRatio="none" className="h-full w-full">
        <path
          d="M0,60 C240,15 480,95 720,55 C960,15 1200,95 1440,50 L1440,100 L0,100 Z"
          fill={fill}
        />
      </svg>
    </div>
  );
}
