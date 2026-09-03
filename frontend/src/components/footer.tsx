import { PaperAirplane } from "@/components/paper-airplane";
import { Reveal } from "@/components/reveal";

const COLUMNS: { heading: string; links: { label: string; href: string }[] }[] = [
  {
    heading: "Product",
    links: [
      { label: "How it works", href: "#forecast" },
      { label: "Track record", href: "#track-record" },
      { label: "Run a forecast", href: "#forecast" },
    ],
  },
  {
    heading: "Resources",
    links: [
      { label: "API reference", href: "/api/backend/docs" },
      { label: "Source on GitHub", href: "https://github.com/okayniti/runway" },
    ],
  },
];

export function Footer() {
  return (
    <Reveal>
      <footer className="relative border-t border-line px-6 py-16">
        <PaperAirplane size={30} rotate={-14} className="absolute right-8 top-10 sm:right-16" bobDelay={0.6} />
        <div className="mx-auto flex max-w-5xl flex-col gap-12 sm:flex-row sm:justify-between">
          <div>
            <p className="font-display text-xl italic font-semibold text-ink">runway</p>
            <p className="mt-3 max-w-xs text-sm text-ink-muted">
              Cash-flow forecasting that tells you what&rsquo;s coming, plainly,
              with a track record you can check.
            </p>
          </div>

          <div className="flex gap-16">
            {COLUMNS.map((col) => (
              <div key={col.heading}>
                <p className="text-sm font-medium text-ink">{col.heading}</p>
                <ul className="mt-4 space-y-3">
                  {col.links.map((link) => (
                    <li key={link.label}>
                      <a
                        href={link.href}
                        className="text-sm text-ink-muted transition-colors hover:text-ink"
                      >
                        {link.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div className="mx-auto mt-16 max-w-5xl border-t border-line pt-8 text-xs text-ink-faint">
          <p>
            Replaces manual weekly cash reviews with continuous, automated monitoring — the
            cost shifts from a person&rsquo;s recurring time to API/compute, not headcount.
          </p>
          <p className="mt-2">A single-tenant demo of a multi-tenant-shaped forecasting agent.</p>
        </div>
      </footer>
    </Reveal>
  );
}
