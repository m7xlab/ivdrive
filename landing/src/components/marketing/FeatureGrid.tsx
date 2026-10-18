"use client";

import {
  BatteryCharging,
  Bot,
  Gauge,
  MapPinned,
  Route,
  Waves,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { RevealGroup, RevealItem } from "./Reveal";

const features: {
  icon: LucideIcon;
  title: string;
  body: string;
}[] = [
  {
    icon: Route,
    title: "Trips & routes",
    body: "Every drive mapped with elevation, efficiency and climate context — not just start and end pins.",
  },
  {
    icon: BatteryCharging,
    title: "Charging intelligence",
    body: "Sessions, curves, integrals and real €/kWh economics across home, work and public networks.",
  },
  {
    icon: Gauge,
    title: "Battery health (SoH)",
    body: "Multi-method state-of-health with confidence, degradation curves and a monthly health passport.",
  },
  {
    icon: Waves,
    title: "Vampire drain & SoC",
    body: "See idle losses clearly. Predictive arrival SOC so you plan charges before the dashboard blinks.",
  },
  {
    icon: MapPinned,
    title: "ABRP live telemetry",
    body: "Optional push of SOC, charging and position to A Better Route Planner for smarter routes.",
  },
  {
    icon: Bot,
    title: "AI support coach",
    body: "Ask questions in plain language. Get charts, explanations and next steps from your own data.",
  },
];

export function FeatureGrid() {
  return (
    <section className="section-pad relative">
      <div className="container-x">
        <RevealGroup className="mx-auto max-w-2xl text-center">
          <RevealItem>
            <p className="text-[0.78rem] font-semibold uppercase tracking-[0.22em] text-cyan">
              Built for drivers who want the truth
            </p>
            <h2 className="font-display mt-4 text-[clamp(2.1rem,5vw,3.5rem)] font-bold leading-[1.08]">
              Depth that OEM dashboards
              <span className="text-gradient"> never show</span>
            </h2>
            <p className="mt-5 text-lg leading-relaxed text-muted">
              iVDrive turns raw vehicle telemetry into decisions — when to charge,
              how your pack ages, and where energy really goes.
            </p>
          </RevealItem>
        </RevealGroup>

        <RevealGroup className="mt-16 grid gap-5 sm:grid-cols-2 lg:grid-cols-3" stagger={0.08}>
          {features.map((f) => (
            <RevealItem key={f.title}>
              <article className="group relative h-full overflow-hidden rounded-[22px] border border-white/[0.07] bg-gradient-to-b from-white/[0.045] to-transparent p-7 transition-all duration-300 hover:-translate-y-1 hover:border-cyan/25 hover:shadow-[0_20px_60px_rgba(0,212,255,0.08)]">
                <div className="absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-emerald/50 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
                <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 bg-emerald/10 text-emerald-bright">
                  <f.icon className="h-5 w-5" />
                </div>
                <h3 className="font-display mt-5 text-xl font-semibold">{f.title}</h3>
                <p className="mt-2.5 text-[0.95rem] leading-relaxed text-muted">{f.body}</p>
              </article>
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  );
}
