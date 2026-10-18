import { ArrowUpRight, Github, HeartHandshake, Milestone } from "lucide-react";
import { CTAButton } from "./CTAButton";
import { Reveal, RevealGroup, RevealItem } from "./Reveal";

export function CommunitySection() {
  return (
    <section className="section-pad">
      <div className="container-x">
        <div className="relative overflow-hidden rounded-[28px] border border-white/[0.08] bg-gradient-to-br from-[#121a2e] via-[#0c1222] to-[#0a0e1a] p-10 md:p-14">
          <div
            aria-hidden
            className="absolute right-0 top-0 h-72 w-72 rounded-full bg-cyan/10 blur-[80px]"
          />
          <div
            aria-hidden
            className="absolute bottom-0 left-0 h-64 w-64 rounded-full bg-emerald/10 blur-[80px]"
          />

          <div className="relative grid gap-12 lg:grid-cols-2 lg:items-center">
            <div>
              <Reveal>
                <p className="text-[0.78rem] font-semibold uppercase tracking-[0.22em] text-cyan">
                  Community
                </p>
                <h2 className="font-display mt-4 text-[clamp(2rem,4.5vw,3.15rem)] font-bold leading-[1.1]">
                  Built in public with people who care about their cars
                </h2>
                <p className="mt-5 max-w-lg text-lg leading-relaxed text-muted">
                  Feature ideas, bug reports, docs, and pull requests all shape
                  the roadmap. If you drive a Škoda iV — or want to help the next
                  VW Group brand land — there’s a seat at the table.
                </p>
                <div className="mt-8 flex flex-wrap gap-3">
                  <CTAButton href="/roadmap/">
                    <Github className="h-4 w-4" />
                    View roadmap
                  </CTAButton>
                  <CTAButton href="/community/" variant="ghost">
                    How to contribute
                  </CTAButton>
                </div>
              </Reveal>
            </div>

            <RevealGroup className="grid gap-4" stagger={0.12}>
              <RevealItem>
                <a
                  href="https://github.com/m7xlab/iVDrive/issues"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group flex items-start gap-4 rounded-2xl border border-white/[0.07] bg-white/[0.03] p-5 transition-colors hover:border-cyan/30"
                >
                  <HeartHandshake className="mt-0.5 h-5 w-5 text-emerald-bright" />
                  <div>
                    <p className="font-semibold">Contributions welcome</p>
                    <p className="mt-1 text-sm text-muted">
                      Issues, ideas and PRs — from typo fixes to new analytics.
                    </p>
                  </div>
                  <ArrowUpRight className="ml-auto h-4 w-4 text-faint transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-cyan" />
                </a>
              </RevealItem>
              <RevealItem>
                <a
                  href="/roadmap/"
                  className="group flex items-start gap-4 rounded-2xl border border-white/[0.07] bg-white/[0.03] p-5 transition-colors hover:border-cyan/30"
                >
                  <Milestone className="mt-0.5 h-5 w-5 text-cyan" />
                  <div>
                    <p className="font-semibold">Transparent roadmap</p>
                    <p className="mt-1 text-sm text-muted">
                      Škoda first. More VW Group brands next. Always in the open.
                    </p>
                  </div>
                  <ArrowUpRight className="ml-auto h-4 w-4 text-faint transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-cyan" />
                </a>
              </RevealItem>
            </RevealGroup>
          </div>
        </div>
      </div>
    </section>
  );
}
