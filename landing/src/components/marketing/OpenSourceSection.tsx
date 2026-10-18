import { Boxes, Cloud, Github, ShieldCheck } from "lucide-react";
import { CTAButton } from "./CTAButton";
import { Reveal, RevealGroup, RevealItem } from "./Reveal";

const points = [
  {
    icon: Github,
    title: "Elastic License 2.0 (ELv2)",
    body: "Use it, self-host it, extend it. Not a locked cloud silo.",
  },
  {
    icon: Boxes,
    title: "Docker Compose stack",
    body: "API, collector, Postgres and Valkey — one `compose up` away.",
  },
  {
    icon: ShieldCheck,
    title: "Your credentials, your box",
    body: "Vehicle secrets stay in your deployment. We never need them.",
  },
  {
    icon: Cloud,
    title: "Hosted beta optional",
    body: "Prefer no setup? Request an invite at ivdrive.eu and drive.",
  },
];

export function OpenSourceSection() {
  return (
    <section className="section-pad relative overflow-hidden">
      <div
        aria-hidden
        className="absolute left-1/2 top-0 h-[420px] w-[820px] -translate-x-1/2 rounded-full bg-emerald/[0.08] blur-[100px]"
      />
      <div className="container-x relative">
        <div className="grid items-start gap-14 lg:grid-cols-[1.1fr_1fr]">
          <div>
            <Reveal>
              <p className="text-[0.78rem] font-semibold uppercase tracking-[0.22em] text-cyan">
                Open source & self-hostable
              </p>
              <h2 className="font-display mt-4 text-[clamp(2.1rem,5vw,3.5rem)] font-bold leading-[1.08]">
                Community-driven.
                <br />
                <span className="text-gradient">You keep the keys.</span>
              </h2>
              <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted">
                iVDrive is built in the open for people who want TeslaMate-grade
                depth on VW Group EVs — without handing a third party the keys to
                their car.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <CTAButton href="https://github.com/m7xlab/iVDrive" target="_blank" rel="noopener noreferrer">
                  <Github className="h-4 w-4" />
                  View on GitHub
                </CTAButton>
                <CTAButton href="/open-source/" variant="ghost">
                  Self-hosting guide
                </CTAButton>
              </div>
            </Reveal>
          </div>

          <RevealGroup className="grid gap-4 sm:grid-cols-2">
            {points.map((p) => (
              <RevealItem key={p.title}>
                <div className="h-full rounded-[20px] border border-white/[0.07] bg-white/[0.025] p-6">
                  <p.icon className="h-5 w-5 text-emerald-bright" />
                  <h3 className="font-display mt-4 text-lg font-semibold">{p.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted">{p.body}</p>
                </div>
              </RevealItem>
            ))}
          </RevealGroup>
        </div>
      </div>
    </section>
  );
}
