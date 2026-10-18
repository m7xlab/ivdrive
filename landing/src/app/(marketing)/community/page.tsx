import type { Metadata } from "next";
import { Github, MessagesSquare, Puzzle, Rocket } from "lucide-react";
import { Reveal, RevealGroup, RevealItem } from "@/components/marketing/Reveal";
import { CTAButton } from "@/components/marketing/CTAButton";
import { BetaCTA } from "@/components/marketing/BetaCTA";

export const metadata: Metadata = {
  title: "Community",
  description:
    "Join the iVDrive community — GitHub discussions, issues, roadmap and contributions for VW Group EV owners.",
  alternates: { canonical: "https://ivdrive.eu/community/" },
};

const ways = [
  {
    icon: MessagesSquare,
    title: "Discussions",
    body: "Share how you use iVDrive, ask for advice, and shape what we build next.",
    href: "https://github.com/m7xlab/iVDrive/discussions",
  },
  {
    icon: Puzzle,
    title: "Contribute",
    body: "Bug reports, docs, translations, analytics — every improvement counts.",
    href: "https://github.com/m7xlab/iVDrive/blob/main/CONTRIBUTING.md",
  },
  {
    icon: Rocket,
    title: "Roadmap",
    body: "Škoda first. More VW Group brands where the Connect APIs allow.",
    href: "https://github.com/m7xlab/iVDrive/blob/main/ROADMAP.md",
  },
];

export default function CommunityPage() {
  return (
    <>
      <section className="relative pb-16 pt-[130px]">
        <div className="container-x max-w-3xl">
          <Reveal>
            <p className="text-[0.78rem] font-semibold uppercase tracking-[0.22em] text-cyan">
              Community
            </p>
            <h1 className="font-display mt-4 text-[clamp(2.5rem,6vw,4.25rem)] font-bold leading-[1.05]">
              Built with drivers,
              <span className="text-gradient"> not for them</span>
            </h1>
            <p className="mt-6 text-xl leading-relaxed text-muted">
              iVDrive is open source and community-driven. Whether you fix a typo
              or design the next battery estimator — you’re part of the product.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <CTAButton
                href="https://github.com/m7xlab/iVDrive"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Github className="h-4 w-4" />
                GitHub
              </CTAButton>
              <CTAButton href="https://app.ivdrive.eu/register" variant="ghost">
                Join the beta
              </CTAButton>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="pb-20">
        <div className="container-x">
          <RevealGroup className="grid gap-5 md:grid-cols-3">
            {ways.map((w) => (
              <RevealItem key={w.title}>
                <a
                  href={w.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group flex h-full flex-col rounded-[22px] border border-white/[0.07] bg-white/[0.025] p-7 transition-all hover:-translate-y-1 hover:border-cyan/25"
                >
                  <w.icon className="h-5 w-5 text-emerald-bright" />
                  <h2 className="font-display mt-4 text-xl font-semibold">{w.title}</h2>
                  <p className="mt-2.5 flex-1 leading-relaxed text-muted">{w.body}</p>
                  <span className="mt-5 text-sm text-cyan opacity-80 transition-opacity group-hover:opacity-100">
                    Open on GitHub →
                  </span>
                </a>
              </RevealItem>
            ))}
          </RevealGroup>
        </div>
      </section>

      <BetaCTA />
    </>
  );
}
