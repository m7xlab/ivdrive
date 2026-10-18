import { ArrowRight } from "lucide-react";
import { CTAButton } from "./CTAButton";
import { Reveal } from "./Reveal";

export function BetaCTA() {
  return (
    <section className="relative pb-28 pt-8">
      <div className="container-x">
        <Reveal>
          <div className="relative overflow-hidden rounded-[32px] border border-white/[0.08] bg-gradient-to-r from-[#0d1a14] via-[#0c1224] to-[#0a1520] px-8 py-16 text-center md:px-16 md:py-20">
            <div
              aria-hidden
              className="absolute left-1/2 top-0 h-[320px] w-[520px] -translate-x-1/2 rounded-full bg-emerald/20 blur-[90px]"
            />
            <div
              aria-hidden
              className="absolute bottom-0 right-10 h-[220px] w-[220px] rounded-full bg-cyan/15 blur-[70px]"
            />

            <div className="relative">
              <h2 className="font-display text-[clamp(2.2rem,5.5vw,3.75rem)] font-bold leading-[1.06]">
                Ready to see your EV
                <span className="text-gradient"> for real?</span>
              </h2>
              <p className="mx-auto mt-5 max-w-xl text-lg text-muted">
                Request an invite for the hosted beta — or clone the repo and run
                the full stack on your own hardware tonight.
              </p>
              <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
                <CTAButton href="/register">
                  Request invite
                  <ArrowRight className="h-4 w-4" />
                </CTAButton>
                <CTAButton
                  href="https://github.com/m7xlab/iVDrive"
                  variant="ghost"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Self-host on GitHub
                </CTAButton>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
