import type { Metadata } from "next";
import { Coffee, Heart, Server, Sparkles } from "lucide-react";
import { Reveal, RevealGroup, RevealItem } from "@/components/marketing/Reveal";
import { CTAButton, CTAAnchor } from "@/components/marketing/CTAButton";

export const metadata: Metadata = {
  title: "Sponsor iVDrive",
  description:
    "iVDrive is built and hosted by one person. Sponsorships keep the domain, servers and development sustainable.",
  alternates: { canonical: "https://ivdrive.eu/sponsors/" },
};

const uses = [
  {
    icon: Server,
    title: "Hosting & domain",
    body: "ivdrive.eu, compute, database backups and monitoring for the public beta.",
  },
  {
    icon: Sparkles,
    title: "Development time",
    body: "Features, analytics depth, security work and docs — mostly evenings and weekends.",
  },
  {
    icon: Coffee,
    title: "Sustainability",
    body: "A small recurring budget keeps the project alive long-term, not just for a launch week.",
  },
];

export default function SponsorsPage() {
  return (
    <>
      <section className="relative overflow-hidden pb-16 pt-[130px]">
        <div
          aria-hidden
          className="absolute left-1/2 top-20 h-[360px] w-[560px] -translate-x-1/2 rounded-full bg-emerald/15 blur-[100px]"
        />
        <div className="container-x relative max-w-3xl text-center">
          <Reveal>
            <p className="text-[0.78rem] font-semibold uppercase tracking-[0.22em] text-cyan">
              Community powered
            </p>
            <h1 className="font-display mt-4 text-[clamp(2.5rem,6vw,4.25rem)] font-bold leading-[1.05]">
              Built by one person.
              <br />
              <span className="text-gradient">Kept alive by the community.</span>
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-xl leading-relaxed text-muted">
              iVDrive has no corporate sponsor and no venture budget. If it helps
              you understand your Škoda or VW Group EV, a small contribution helps
              cover servers, the domain and continued development.
            </p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
              <CTAAnchor
                href="https://github.com/sponsors/m7xlab"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Heart className="h-4 w-4" />
                Become a sponsor
              </CTAAnchor>
              <CTAAnchor
                href="https://ko-fi.com/m7xlaboratory"
                target="_blank"
                rel="noopener noreferrer"
                variant="ghost"
              >
                <Coffee className="h-4 w-4" />
                Buy me a coffee
              </CTAAnchor>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="pb-16">
        <div className="container-x">
          <RevealGroup className="grid gap-5 md:grid-cols-3">
            {uses.map((u) => (
              <RevealItem key={u.title}>
                <div className="h-full rounded-[22px] border border-white/[0.07] bg-white/[0.025] p-7">
                  <u.icon className="h-5 w-5 text-emerald-bright" />
                  <h2 className="font-display mt-4 text-xl font-semibold">{u.title}</h2>
                  <p className="mt-2.5 leading-relaxed text-muted">{u.body}</p>
                </div>
              </RevealItem>
            ))}
          </RevealGroup>
        </div>
      </section>

      <section className="pb-24">
        <div className="container-x">
          <Reveal>
            <div className="rounded-[28px] border border-white/[0.08] bg-gradient-to-br from-[#121a2e] via-[#0c1222] to-[#0a0e1a] p-10 text-center">
              <h2 className="font-display text-2xl font-semibold">Other ways to help</h2>
              <p className="mx-auto mt-3 max-w-xl text-muted">
                Money is not the only fuel. Stars, feedback, bug reports and PRs
                move the project just as much.
              </p>
              <div className="mt-7 flex flex-wrap justify-center gap-3">
                <CTAButton href="/community/">Contribute</CTAButton>
                <CTAAnchor
                  href="https://github.com/m7xlab/iVDrive"
                  variant="ghost"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Star on GitHub
                </CTAAnchor>
                <CTAButton href="https://app.ivdrive.eu/register" variant="ghost">
                  Join the beta
                </CTAButton>
              </div>
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
