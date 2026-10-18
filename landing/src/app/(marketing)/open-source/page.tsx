import type { Metadata } from "next";
import { Boxes, Github, Lock, Server } from "lucide-react";
import { Reveal, RevealGroup, RevealItem } from "@/components/marketing/Reveal";
import { CTAButton } from "@/components/marketing/CTAButton";
import { BetaCTA } from "@/components/marketing/BetaCTA";

export const metadata: Metadata = {
  title: "Open Source & Self-Hosting",
  description:
    "iVDrive is self-hostable with Docker Compose under the Elastic License 2.0 (ELv2). Keep vehicle data on your own infrastructure.",
  alternates: { canonical: "https://ivdrive.eu/open-source/" },
};

const cards = [
  {
    icon: Server,
    title: "Full stack, one compose file",
    body: "Frontend (Next.js), FastAPI backend, collector worker, PostgreSQL and Valkey — orchestrated with Docker Compose.",
  },
  {
    icon: Lock,
    title: "Your vehicle credentials stay local",
    body: "Connect secrets live in your environment. Perfect for owners who want insight without a third-party silo.",
  },
  {
    icon: Boxes,
    title: "Extend and contribute",
    body: "REST API, collector hooks, and a growing statistics suite. PRs and feature ideas are part of the product.",
  },
  {
    icon: Github,
    title: "Elastic License 2.0 (ELv2)",
    body: "Use and modify freely for yourself and your org. Just don’t offer iVDrive as a managed third-party service.",
  },
];

export default function OpenSourcePage() {
  return (
    <>
      <section className="relative pb-16 pt-[130px]">
        <div className="container-x max-w-3xl">
          <Reveal>
            <p className="text-[0.78rem] font-semibold uppercase tracking-[0.22em] text-cyan">
              Open source
            </p>
            <h1 className="font-display mt-4 text-[clamp(2.5rem,6vw,4.25rem)] font-bold leading-[1.05]">
              Run it yourself.
              <span className="text-gradient"> Own the stack.</span>
            </h1>
            <p className="mt-6 text-xl leading-relaxed text-muted">
              Hosted beta for convenience. Self-hosting for control. The same
              product either way — designed so enthusiasts can run deep EV
              analytics on a NAS, a VPS, or a spare box at home.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <CTAButton
                href="https://github.com/m7xlab/iVDrive"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Github className="h-4 w-4" />
                Clone the repo
              </CTAButton>
              <CTAButton href="/register" variant="ghost">
                Prefer hosted? Request invite
              </CTAButton>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="pb-20">
        <div className="container-x">
          <RevealGroup className="grid gap-5 sm:grid-cols-2">
            {cards.map((c) => (
              <RevealItem key={c.title}>
                <div className="h-full rounded-[22px] border border-white/[0.07] bg-white/[0.025] p-7">
                  <c.icon className="h-5 w-5 text-emerald-bright" />
                  <h2 className="font-display mt-4 text-xl font-semibold">{c.title}</h2>
                  <p className="mt-2.5 leading-relaxed text-muted">{c.body}</p>
                </div>
              </RevealItem>
            ))}
          </RevealGroup>

          <Reveal className="mt-12">
            <div className="rounded-[22px] border border-white/[0.08] bg-abyss p-8">
              <h2 className="font-display text-xl font-semibold">Quick start (self-host)</h2>
              <pre className="mt-4 overflow-x-auto rounded-xl border border-white/[0.06] bg-black/40 p-5 text-sm leading-relaxed text-muted">
{`git clone https://github.com/m7xlab/iVDrive.git
cd iVDrive
cp .env.example .env   # set secrets
docker compose up -d
# Web UI → http://localhost:3000`}
              </pre>
              <p className="mt-4 text-sm text-faint">
                Full instructions live in the repository docs — including DB init and admin promotion.
              </p>
            </div>
          </Reveal>
        </div>
      </section>

      <BetaCTA />
    </>
  );
}
