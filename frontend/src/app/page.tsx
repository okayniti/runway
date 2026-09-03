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
