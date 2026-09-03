import { CapabilityMarquee } from "@/components/capability-marquee";
import { FeaturesGrid } from "@/components/features-grid";
import { Footer } from "@/components/footer";
import { Hero } from "@/components/hero";
import { LiveForecastPanel } from "@/components/live-forecast-panel";
import { Nav } from "@/components/nav";
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
        <TrackRecord />
      </main>
      <Footer />
    </>
  );
}
