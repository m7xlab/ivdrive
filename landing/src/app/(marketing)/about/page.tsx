import type { Metadata } from "next";
import { FlaskConical, HeartHandshake, Scale, Sparkles } from "lucide-react";
import { Reveal, RevealGroup, RevealItem } from "@/components/marketing/Reveal";
import { CTAButton, CTAAnchor } from "@/components/marketing/CTAButton";
import { BetaCTA } from "@/components/marketing/BetaCTA";

export const metadata: Metadata = {
  title: "About",
  description:
    "iVDrive is built by m7xlab — an independent data lab. Premium, self-hostable EV telemetry for Škoda fully electric vehicles and the wider VW Group.",
  alternates: { canonical: "https://ivdrive.eu/about/" },
};

const values = [
  {
    icon: Scale,
    title: "Answers over dashboards",
    body: "Factory apps show a number. iVDrive shows the story behind it — curves, costs, climate and elevation effects, and long-term battery health.",
  },
  {
    icon: FlaskConical,
    title: "Built by m7xlab",
    body: "iVDrive is a flagship project of m7xlab — an independent data lab. We design for clarity, ship in public, and treat infrastructure as a craft.",
  },
  {
    icon: HeartHandshake,
    title: "Ownership by default",
    body: "Self-hosting is a first-class path. Your vehicle data should not require a permanent third party. Škoda fully electric first; more VW Group EVs next.",
  },
  {
    icon: Sparkles,
    title: "Invite-only beta",
    body: "We scale carefully so the hosted service stays stable while the product matures with real drivers and shared vehicle data.",
  },
];

export default function AboutPage() {
  return (
    <>
      <section className="relative pb-16 pt-[130px]">
        <div className="container-x max-w-3xl">
          <Reveal>
            <p className="text-[0.78rem] font-semibold uppercase tracking-[0.22em] text-cyan">
              About
            </p>
            <h1 className="font-display mt-4 text-[clamp(2.5rem,6vw,4.25rem)] font-bold leading-[1.05]">
              Premium EV intelligence
              <span className="text-gradient"> for VW Group</span>
            </h1>
            <p className="mt-6 text-xl leading-relaxed text-muted">
              iVDrive exists because modern EVs generate extraordinary data — and
              drivers deserve better than a thin summary screen. We turn that
              telemetry into clarity: for trips, charging, efficiency and battery
              life.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <CTAButton href="/register">Request invite</CTAButton>
              <CTAButton href="/features/" variant="ghost">
                Explore features
              </CTAButton>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="pb-16">
        <div className="container-x">
          <Reveal>
            <div className="rounded-[28px] border border-white/[0.08] bg-gradient-to-br from-[#121a2e] via-[#0c1222] to-[#0a0e1a] p-10">
              <p className="text-[0.78rem] font-semibold uppercase tracking-[0.2em] text-cyan">
                Who we are
              </p>
              <h2 className="font-display mt-3 text-[clamp(1.75rem,3.5vw,2.5rem)] font-bold">
                A lab for people who love data.
              </h2>
              <div className="mt-5 grid gap-5 text-lg leading-relaxed text-muted md:grid-cols-2">
                <p>
                  <strong className="text-ink">m7xlab</strong> is an independent
                  organization of engineers and data practitioners. We ship tools
                  we wish we had ourselves — for people who care about metrics,
                  pipelines and honest numbers.
                </p>
                <p>
                  iVDrive is our electric-mobility flagship: independent vehicle
                  statistics, no vendor bias. We design for clarity, work in
                  public, and keep the stack something you can run yourself.
                </p>
              </div>
              <div className="mt-8 flex flex-wrap gap-3">
                <CTAAnchor
                  href="https://m7xlab.top"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Visit m7xlab.top
                </CTAAnchor>
                <CTAButton href="/sponsors/" variant="ghost">
                  Support iVDrive
                </CTAButton>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="pb-20">
        <div className="container-x">
          <RevealGroup className="grid gap-5 sm:grid-cols-2">
            {values.map((v) => (
              <RevealItem key={v.title}>
                <div className="h-full rounded-[22px] border border-white/[0.07] bg-gradient-to-b from-white/[0.04] to-transparent p-7">
                  <v.icon className="h-5 w-5 text-emerald-bright" />
                  <h2 className="font-display mt-4 text-xl font-semibold">{v.title}</h2>
                  <p className="mt-3 leading-relaxed text-muted">{v.body}</p>
                </div>
              </RevealItem>
            ))}
          </RevealGroup>
        </div>
      </section>

      <BetaCTA />
    </>
  );
}
