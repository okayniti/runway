import { CapabilityMarquee } from "@/components/capability-marquee";
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
        <TrackRecord />
      </main>
    </>
  );
}
