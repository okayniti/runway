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
      <Footer />
    </>
  );
}
