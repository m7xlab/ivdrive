import type { Metadata } from "next";
import {
  BatteryCharging,
  Bot,
  Gauge,
  MapPinned,
  Route,
  Waves,
  type LucideIcon,
} from "lucide-react";
import { Reveal, RevealGroup, RevealItem } from "@/components/marketing/Reveal";
import { CTAButton } from "@/components/marketing/CTAButton";
import { BetaCTA } from "@/components/marketing/BetaCTA";

export const metadata: Metadata = {
  title: "Features",
  description:
    "Trips, charging curves, multi-method battery SoH, vampire drain, predictive SoC, ABRP and an AI coach — the full iVDrive feature set.",
  alternates: { canonical: "https://ivdrive.eu/features/" },
};

const features: {
  icon: LucideIcon;
  title: string;
  body: string;
  details: string[];
}[] = [
  {
    icon: Route,
    title: "Trips & route efficiency",
    body: "See every drive with the context that matters for range.",
    details: [
      "Trip history with map traces",
      "Elevation and climate penalties",
      "Speed × temperature efficiency matrix",
      "Visited places and geofences (home / work)",
    ],
  },
  {
    icon: BatteryCharging,
    title: "Charging intelligence",
    body: "From session curves to real cost per kilowatt-hour.",
    details: [
      "Session browser and statistics",
      "Charging curves and integrals",
      "Home / public rate economics",
      "Charging plans and subscription matching",
    ],
  },
  {
    icon: Gauge,
    title: "Battery health (SoH v2)",
    body: "Six methods, one trustworthy number — with confidence.",
    details: [
      "Capacity-based estimators",
      "Charging-curve taper analysis",
      "Cell imbalance & throughput models",
      "Fleet benchmark + range drift",
      "Monthly Battery Health Passport",
    ],
  },
  {
    icon: Waves,
    title: "Vampire drain & predictive SoC",
    body: "Idle losses and arrival estimates you can plan around.",
    details: [
      "Vampire drain monitoring",
      "Predictive / arrival SoC",
      "Mileage forecast trends",
    ],
  },
  {
    icon: MapPinned,
    title: "ABRP live telemetry",
    body: "Optional integration for smarter long-route planning.",
    details: [
      "Push SOC, charging and position",
      "Opt-in and encrypted credentials",
      "Driving / charging data only (ABRP-side limits)",
    ],
  },
  {
    icon: Bot,
    title: "AI Support Coach",
    body: "Ask in plain language. Get charts and explanations.",
    details: [
      "Conversation over your own data",
      "Chart rendering from queries",
      "Helpful nudges, not noise",
    ],
  },
];

export default function FeaturesPage() {
  return (
    <>
      <section className="relative pb-16 pt-[130px]">
        <div className="container-x max-w-3xl">
          <Reveal>
            <p className="text-[0.78rem] font-semibold uppercase tracking-[0.22em] text-cyan">
              Features
            </p>
            <h1 className="font-display mt-4 text-[clamp(2.5rem,6vw,4.25rem)] font-bold leading-[1.05]">
              Everything your OEM app
              <span className="text-gradient"> won’t tell you</span>
            </h1>
            <p className="mt-6 text-xl leading-relaxed text-muted">
              iVDrive is a single dashboard for trips, charging, efficiency and
              battery health — with analytics built for people who actually care
              about the electrons.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <CTAButton href="/register">Request invite</CTAButton>
              <CTAButton href="/" variant="ghost">
                Back to home
              </CTAButton>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="pb-24">
        <div className="container-x">
          <RevealGroup className="grid gap-6 md:grid-cols-2">
            {features.map((f) => (
              <RevealItem key={f.title}>
                <article className="h-full rounded-[24px] border border-white/[0.07] bg-white/[0.025] p-8">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 bg-emerald/10 text-emerald-bright">
                    <f.icon className="h-5 w-5" />
                  </div>
                  <h2 className="font-display mt-5 text-2xl font-semibold">{f.title}</h2>
                  <p className="mt-2 text-muted">{f.body}</p>
                  <ul className="mt-5 space-y-2">
                    {f.details.map((d) => (
                      <li key={d} className="flex gap-2.5 text-[0.95rem] text-muted">
                        <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan" />
                        {d}
                      </li>
                    ))}
                  </ul>
                </article>
              </RevealItem>
            ))}
          </RevealGroup>
        </div>
      </section>

      <BetaCTA />
    </>
  );
}
