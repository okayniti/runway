import { CalibrationSpotlight } from "@/components/calibration-spotlight";
import { CapabilityMarquee } from "@/components/capability-marquee";
import { FeaturesGrid } from "@/components/features-grid";
import { Footer } from "@/components/footer";
import { Hero } from "@/components/hero";
import { LiveForecastPanel } from "@/components/live-forecast-panel";
import { Nav } from "@/components/nav";
import { SectionWave } from "@/components/section-wave";
import { TrackRecord } from "@/components/track-record";

export default function Home() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        {/* Third color/seam: recolored the marquee strip from paper-dim to
            ember-dim (see capability-marquee.tsx) rather than reusing
            ink/paper again -- its own content is forecasting/risk
            capabilities, so the warm tint fits rather than being an
            arbitrary color pick. behindFill isn't overridden here: Hero's
            own background IS var(--color-paper), so the default already
            matches exactly, same as the very first wave's situation.
            maxScaleY is 1 (the scaleY layer fully off) here -- the
            marquee's own py-6 has nowhere near the clearance the other
            two seams have. Tried 1.08 first (a modest 8% instead of the
            default 35%) reasoning that would be safely small; a zoomed
            screenshot showed it still cut through the airplane and pill
            row, so the real constraint wasn't "how much" scaleY but
            whether this seam has room for any of it. The path's own
            amplitude morph (shared with every instance, ~29% swing,
            always bounded inside the viewBox) still reads as more
            pronounced than the pre-this-request ~13% baseline on its
            own, verified the same way after turning scaleY off
            entirely -- clean, no overlap. */}
        <SectionWave fill="var(--color-ember-dim)" maxScaleY={1} />
        <CapabilityMarquee />
        <LiveForecastPanel />
        <FeaturesGrid />
        <SectionWave />
        <CalibrationSpotlight />
        <TrackRecord />
      </main>
      {/* TrackRecord (ink) -> Footer (paper) is the single highest-contrast
          seam on the page (13.42:1, WCAG relative-luminance ratio -- higher
          even than the 11.86:1 seam the wave above already treats) and,
          before this, had no transition at all beyond a 1px border. Every
          other seam is either the same ink-on-ink as this one's neighbor
          (1.00:1, no treatment needed) or paper vs. paper-dim (1.13:1,
          barely perceptible). fill/behindFill are swapped relative to the
          wave above since the dark section is now the one BEFORE the wave
          instead of after it -- see section-wave.tsx's docstring. */}
      <SectionWave fill="var(--color-paper)" behindFill="var(--color-ink)" />
      <Footer />
    </>
  );
}
