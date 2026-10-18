"use client";

import { motion, useReducedMotion } from "motion/react";
import { ArrowRight, Play } from "lucide-react";
import { CTAButton } from "./CTAButton";
import { GradientAurora } from "./GradientAurora";

const fadeUp = {
  hidden: { opacity: 0, y: 32, filter: "blur(10px)" },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: {
      duration: 0.9,
      delay: 0.12 * i,
      ease: [0.22, 1, 0.36, 1] as const,
    },
  }),
};

export function Hero() {
  const reduce = useReducedMotion();

  return (
    <section className="relative overflow-hidden pb-24 pt-[120px] md:pb-32 md:pt-[150px]">
      <GradientAurora />
      <div className="grid-fade absolute inset-0" aria-hidden />

      <div className="container-x relative">
        <motion.div
          initial={reduce ? false : "hidden"}
          animate="show"
          className="mx-auto max-w-4xl text-center"
        >
          <motion.div
            custom={0}
            variants={fadeUp}
            className="mx-auto inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3.5 py-1.5 text-[0.78rem] text-muted"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-emerald shadow-[0_0_10px_rgba(75,168,46,0.9)]" />
            Invite-only beta · Open telemetry for Škoda iV
          </motion.div>

          <motion.h1
            custom={1}
            variants={fadeUp}
            className="font-display mt-7 text-[clamp(2.75rem,8vw,5.75rem)] font-bold leading-[0.98]"
          >
            <span className="text-gradient-soft">Every charge.</span>
            <br />
            <span className="text-gradient-soft">Every trip.</span>
            <br />
            <span className="text-gradient">Every percent.</span>
          </motion.h1>

          <motion.p
            custom={2}
            variants={fadeUp}
            className="mx-auto mt-7 max-w-2xl text-[1.1rem] leading-relaxed text-muted md:text-[1.22rem]"
          >
            Premium EV data monitoring for Volkswagen Group vehicles — trips,
            charging curves, battery health, and deep analytics in one place.
            Self-host it, or join the hosted beta at ivdrive.eu.
          </motion.p>

          <motion.div
            custom={3}
            variants={fadeUp}
            className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row"
          >
            <CTAButton href="https://app.ivdrive.eu/register">
              Request invite
              <ArrowRight className="h-4 w-4" />
            </CTAButton>
            <CTAButton href="https://app.ivdrive.eu/login" variant="ghost">
              Sign in
            </CTAButton>
            <a
              href="#product"
              className="inline-flex items-center gap-2 px-2 py-2 text-sm text-muted transition-colors hover:text-ink"
            >
              <Play className="h-3.5 w-3.5 fill-current" />
              See it in action
            </a>
          </motion.div>
        </motion.div>

        <motion.div
          initial={reduce ? false : { opacity: 0, y: 60, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 1.1, delay: 0.55, ease: [0.22, 1, 0.36, 1] }}
          className="relative mx-auto mt-16 w-full max-w-5xl"
        >
          <div
            aria-hidden
            className="absolute -inset-x-8 -top-8 bottom-0 rounded-[32px] bg-gradient-to-r from-emerald/15 via-cyan/10 to-transparent blur-2xl"
          />
          <div className="device-frame relative">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/marketing/homepage_dark_theme.png"
              alt="iVDrive vehicle dashboard showing trips, charging and battery overview"
              width={1600}
              height={1000}
              className="w-full"
              loading="eager"
            />
          </div>
          <div
            aria-hidden
            className="pointer-events-none absolute inset-x-10 -bottom-10 h-24 rounded-full bg-emerald/20 blur-3xl"
          />
        </motion.div>
      </div>
    </section>
  );
}
