import { CapabilityMarquee } from "@/components/capability-marquee";
import { Hero } from "@/components/hero";
import { Nav } from "@/components/nav";

export default function Home() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <CapabilityMarquee />
      </main>
    </>
  );
}
