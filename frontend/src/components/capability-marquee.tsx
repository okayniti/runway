import {
  CalendarDays,
  Gauge,
  History,
  ListChecks,
  Receipt,
  TrendingUp,
  Upload,
  Users,
  type LucideIcon,
} from "lucide-react";

// What actually feeds the forecast — real system capabilities, not
// fabricated customer logos. Each of these corresponds to a real,
// working piece of the pipeline (data/, model/, agent/).
const CAPABILITIES: { label: string; icon: LucideIcon }[] = [
  { label: "CSV ledger import", icon: Upload },
  { label: "Recurring payroll detection", icon: Users },
  { label: "Vendor payables tracking", icon: Receipt },
  { label: "Receivables monitoring", icon: TrendingUp },
  { label: "Seasonality-aware modeling", icon: CalendarDays },
  { label: "Confidence scoring on every run", icon: Gauge },
  { label: "Retroactive accuracy backfill", icon: History },
  { label: "Schema-enforced recommendations", icon: ListChecks },
];

function Track() {
  return (
    <div className="flex shrink-0 items-center gap-3 pr-3">
      {CAPABILITIES.map(({ label, icon: Icon }) => (
        <div
          key={label}
          className="flex items-center gap-2.5 rounded-full border border-line bg-paper-card px-5 py-2.5 whitespace-nowrap"
        >
          <Icon className="size-4 text-ember" strokeWidth={1.75} />
          <span className="text-sm text-ink-muted">{label}</span>
        </div>
      ))}
    </div>
  );
}

export function CapabilityMarquee() {
  return (
    <section className="border-y border-line bg-paper-dim py-6">
      <div className="overflow-hidden">
        <div className="animate-marquee flex w-max hover:[animation-play-state:paused]">
          <Track />
          <div aria-hidden="true" className="flex shrink-0">
            <Track />
          </div>
        </div>
      </div>
    </section>
  );
}
