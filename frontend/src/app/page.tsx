import { CapabilityMarquee } from "@/components/capability-marquee";
import { Hero } from "@/components/hero";
import { LiveForecastPanel } from "@/components/live-forecast-panel";
import { Nav } from "@/components/nav";

export default function Home() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <CapabilityMarquee />
        <LiveForecastPanel />
      </main>
    </>
  );
}
