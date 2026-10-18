import type { Metadata } from "next";
import { Car, CheckCircle2, Fuel, Rocket, Sparkles, Users } from "lucide-react";
import { Reveal, RevealGroup, RevealItem } from "@/components/marketing/Reveal";
import { CTAButton, CTAAnchor } from "@/components/marketing/CTAButton";
import { BetaCTA } from "@/components/marketing/BetaCTA";

export const metadata: Metadata = {
  title: "Roadmap",
  description:
    "iVDrive public roadmap: ABRP shipped, VW fully electric in 2027, SEAT EVs late 2027, hybrids in 2028 — and a clear call for owners who can share vehicle data.",
  alternates: { canonical: "https://ivdrive.eu/roadmap/" },
};

const now = [
  {
    title: "Platform built from scratch",
    body: "Web app, API, collector, database and Docker stack — designed and shipped in 2026.",
  },
  {
    title: "Škoda EVs working end-to-end",
    body: "Enyaq iV, Elroq and other Škoda Connect electric models — trips, charging, battery, maps, live status.",
  },
  {
    title: "Deep analytics suite",
    body: "Multi-method SoH, charging curves, climate & elevation penalties, cost estimates.",
  },
  {
    title: "Hosted beta + self-host",
    body: "Invite-only beta at ivdrive.eu and a full Docker Compose stack for your own hardware.",
  },
  {
    title: "Product site & documentation",
    body: "Marketing site, user guides and community scaffolding.",
  },
  {
    title: "ABRP live telemetry",
    body: "Just shipped — optional live SoC / charging / position push to A Better Route Planner.",
  },
];

const timeline = [
  {
    period: "2027 · Q1–Q2",
    title: "Volkswagen fully electric (BEV)",
    body: "Battery-electric VW models — starting with the ID. family (ID.3, ID.4, ID.5, ID.7 and more) and other fully electric VWs where Connect APIs allow. Not petrol/diesel VWs.",
    icon: Car,
    tone: "emerald" as const,
  },
  {
    period: "2027 · Q3–Q4",
    title: "SEAT fully electric (BEV)",
    body: "SEAT / CUPRA battery-electric vehicles (Mii Electric, Born, Tavascan and other SEAT EVs as APIs allow) — electric only, not the petrol lineup. Analytics keep improving all through 2027 via user requests.",
    icon: Rocket,
    tone: "cyan" as const,
  },
  {
    period: "2028 · Q1–Q2",
    title: "Hybrids — fuel + electric together",
    body: "Škoda, VW and SEAT hybrid / PHEV capabilities with combined fuel and electric consumption, cost and efficiency views.",
    icon: Fuel,
    tone: "violet" as const,
  },
];

const supported = [
  { brand: "Škoda", detail: "Enyaq iV, Elroq, other Škoda Connect EVs", status: "Supported · beta" },
  { brand: "Volkswagen", detail: "Fully electric VW (ID. family first, other BEVs as APIs allow)", status: "2027 Q1–Q2" },
  { brand: "SEAT / CUPRA", detail: "Fully electric SEAT / CUPRA (Born, Mii Electric, …)", status: "2027 Q3–Q4" },
  { brand: "Škoda · VW · SEAT", detail: "Hybrids & PHEVs (fuel + electric)", status: "2028 Q1–Q2" },
];

export default function RoadmapPage() {
  return (
    <>
      <section className="relative pb-14 pt-[130px]">
        <div className="container-x max-w-3xl">
          <Reveal>
            <p className="text-[0.78rem] font-semibold uppercase tracking-[0.22em] text-cyan">
              Public roadmap · 2026–2028
            </p>
            <h1 className="font-display mt-4 text-[clamp(2.5rem,6vw,4.25rem)] font-bold leading-[1.05]">
              What we ship next —
              <span className="text-gradient"> and who we need</span>
            </h1>
            <p className="mt-6 text-xl leading-relaxed text-muted">
              We just shipped ABRP. Next comes the wider VW Group — then hybrids.
              Every step is faster when owners share real car data and request the
              metrics that matter.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <CTAButton href="/register">Request invite</CTAButton>
              <CTAAnchor
                href="https://github.com/m7xlab/iVDrive/discussions"
                target="_blank"
                rel="noopener noreferrer"
                variant="ghost"
              >
                Volunteer your model
              </CTAAnchor>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="pb-16">
        <div className="container-x">
          <Reveal>
            <div className="rounded-[24px] border border-emerald/25 bg-emerald/[0.06] p-8">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="h-6 w-6 text-emerald-bright" />
                <h2 className="font-display text-2xl font-semibold">2026 Q1–Q4</h2>
                <span className="rounded-full border border-emerald/30 px-2.5 py-0.5 text-xs text-emerald-bright">
                  Done · built from scratch
                </span>
              </div>
              <RevealGroup className="mt-6 grid gap-4 md:grid-cols-2" stagger={0.06}>
                {now.map((item) => (
                  <RevealItem key={item.title}>
                    <div className="rounded-2xl border border-white/[0.07] bg-white/[0.03] p-5">
                      <p className="font-semibold">{item.title}</p>
                      <p className="mt-1.5 text-sm leading-relaxed text-muted">{item.body}</p>
                    </div>
                  </RevealItem>
                ))}
              </RevealGroup>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="pb-16">
        <div className="container-x">
          <Reveal className="mb-8">
            <h2 className="font-display text-[clamp(1.75rem,3.5vw,2.35rem)] font-bold">
              Timeline
            </h2>
            <p className="mt-2 max-w-2xl text-muted">
              Through 2027 we continuously improve analytics with the community —
              new metrics come from your requests.
            </p>
          </Reveal>
          <div className="space-y-5">
            {timeline.map((t) => (
              <Reveal key={t.title}>
                <div
                  className={`rounded-[22px] border p-7 md:p-8 ${
                    t.tone === "emerald"
                      ? "border-emerald/25 bg-emerald/[0.05]"
                      : t.tone === "cyan"
                        ? "border-cyan/20 bg-cyan/[0.05]"
                        : "border-violet-400/20 bg-violet-400/[0.05]"
                  }`}
                >
                  <div className="flex flex-wrap items-start gap-4">
                    <div
                      className={`flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 ${
                        t.tone === "emerald"
                          ? "bg-emerald/15 text-emerald-bright"
                          : t.tone === "cyan"
                            ? "bg-cyan/15 text-cyan"
                            : "bg-violet-400/15 text-violet-300"
                      }`}
                    >
                      <t.icon className="h-5 w-5" />
                    </div>
                    <div className="flex-1">
                      <p className="text-[0.78rem] font-semibold uppercase tracking-[0.16em] text-faint">
                        {t.period}
                      </p>
                      <h3 className="font-display mt-1 text-xl font-semibold">{t.title}</h3>
                      <p className="mt-2 max-w-3xl leading-relaxed text-muted">{t.body}</p>
                    </div>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="pb-16">
        <div className="container-x">
          <Reveal>
            <div className="relative overflow-hidden rounded-[28px] border border-white/[0.1] bg-gradient-to-br from-[#121a2e] via-[#0c1222] to-[#0a0e1a] p-10">
              <div
                aria-hidden
                className="absolute -right-10 -top-10 h-56 w-56 rounded-full bg-emerald/15 blur-3xl"
              />
              <div className="relative max-w-3xl">
                <div className="flex items-center gap-3">
                  <Users className="h-6 w-6 text-emerald-bright" />
                  <h2 className="font-display text-[clamp(1.65rem,3vw,2.15rem)] font-bold">
                    We need contributors with real cars
                  </h2>
                </div>
                <p className="mt-4 text-lg leading-relaxed text-muted">
                  This roadmap only works if owners share vehicle data and feedback.
                  We especially need drivers of <strong className="text-ink">Volkswagen</strong>,{" "}
                  <strong className="text-ink">SEAT / CUPRA</strong> and other VW Group EVs —
                  later hybrids too.
                </p>
                <ul className="mt-5 space-y-2.5 text-muted">
                  <li className="flex gap-2.5">
                    <Sparkles className="mt-1 h-4 w-4 shrink-0 text-cyan" />
                    Connect your car in the beta (or self-host) and help validate charge curves & SoH
                  </li>
                  <li className="flex gap-2.5">
                    <Sparkles className="mt-1 h-4 w-4 shrink-0 text-cyan" />
                    Request the metrics you want — 2027 analytics is user-driven
                  </li>
                  <li className="flex gap-2.5">
                    <Sparkles className="mt-1 h-4 w-4 shrink-0 text-cyan" />
                    Tell us <em>model + year</em> so we know which brand to unlock next
                  </li>
                </ul>
                <div className="mt-8 flex flex-wrap gap-3">
                  <CTAButton href="/register">Join the beta</CTAButton>
                  <CTAButton href="/sponsors/" variant="ghost">
                    Sponsor the project
                  </CTAButton>
                  <CTAAnchor
                    href="https://github.com/m7xlab/iVDrive/discussions"
                    target="_blank"
                    rel="noopener noreferrer"
                    variant="ghost"
                  >
                    Discuss your vehicle
                  </CTAAnchor>
                </div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="pb-20">
        <div className="container-x">
          <Reveal className="mb-8">
            <h2 className="font-display text-[clamp(1.75rem,3.5vw,2.35rem)] font-bold">
              Supported vehicles
            </h2>
            <p className="mt-2 max-w-2xl text-muted">
              Exact model lists grow as owners contribute data and we validate APIs.
              Don’t see your car? Volunteer as a tester — that is how brands get added.
            </p>
          </Reveal>
          <RevealGroup className="overflow-hidden rounded-[22px] border border-white/[0.08]">
            <div className="grid grid-cols-[1.2fr_1.6fr_1fr] gap-px bg-white/[0.06] text-[0.75rem] font-semibold uppercase tracking-[0.14em] text-faint">
              <div className="bg-void px-5 py-3">Brand</div>
              <div className="bg-void px-5 py-3">Models / API</div>
              <div className="bg-void px-5 py-3">Status</div>
            </div>
            {supported.map((row, i) => (
              <RevealItem key={row.brand}>
                <div
                  className={`grid grid-cols-[1.2fr_1.6fr_1fr] gap-px bg-white/[0.06] ${
                    i === 0 ? "" : ""
                  }`}
                >
                  <div className="bg-[#0b1020] px-5 py-4 font-semibold">{row.brand}</div>
                  <div className="bg-[#0b1020] px-5 py-4 text-muted">{row.detail}</div>
                  <div className="bg-[#0b1020] px-5 py-4">
                    <span
                      className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs ${
                        i === 0
                          ? "border-emerald/40 text-emerald-bright"
                          : "border-white/15 text-muted"
                      }`}
                    >
                      {row.status}
                    </span>
                  </div>
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
