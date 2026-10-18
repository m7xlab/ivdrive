"use client";

import { Reveal, RevealGroup, RevealItem } from "./Reveal";

const beats = [
  {
    tag: "Trips",
    title: "Your roads, in full fidelity",
    body: "Reconstruct every journey with speed, elevation and energy use. Spot the route that silently costs you range — and the one that doesn’t.",
    image: "/marketing/overview_dark_theme.png",
    alt: "iVDrive vehicle overview with live map and system status",
  },
  {
    tag: "Charging",
    title: "Charging curves, not guesswork",
    body: "Session-level power curves, taper points and cost per kWh. Know which chargers are worth the stop — and which are theatre.",
    image: "/marketing/charging_dark_theme.png",
    alt: "iVDrive charging power curve dashboard showing DC taper",
  },
  {
    tag: "Battery",
    title: "Health you can actually trust",
    body: "Six independent SoH methods, weighted median and confidence scoring. Watch degradation over months, not marketing claims.",
    image: "/marketing/soh_dark_theme.png",
    alt: "iVDrive multi-method battery state of health analytics",
  },
];

export function StickyShowcase() {
  return (
    <section id="product" className="section-pad relative">
      <div className="container-x">
        <RevealGroup className="mx-auto max-w-2xl text-center">
          <RevealItem>
            <p className="text-[0.78rem] font-semibold uppercase tracking-[0.22em] text-cyan">
              Product
            </p>
            <h2 className="font-display mt-4 text-[clamp(2.1rem,5vw,3.5rem)] font-bold leading-[1.08]">
              Designed like a product.
              <br />
              <span className="text-gradient">Built like infrastructure.</span>
            </h2>
          </RevealItem>
        </RevealGroup>

        <div className="mt-20 space-y-28">
          {beats.map((beat, i) => (
            <div
              key={beat.tag}
              className={`grid items-center gap-12 lg:grid-cols-2 lg:gap-16 ${
                i % 2 === 1 ? "lg:[&>*:first-child]:order-2" : ""
              }`}
            >
              <Reveal>
                <div className="max-w-xl">
                  <p className="inline-flex rounded-full border border-emerald/30 bg-emerald/10 px-3 py-1 text-[0.75rem] font-semibold uppercase tracking-[0.16em] text-emerald-bright">
                    {beat.tag}
                  </p>
                  <h3 className="font-display mt-5 text-[clamp(1.75rem,3.5vw,2.5rem)] font-bold leading-[1.15]">
                    {beat.title}
                  </h3>
                  <p className="mt-4 text-[1.05rem] leading-relaxed text-muted">{beat.body}</p>
                </div>
              </Reveal>

              <Reveal delay={0.1}>
                <div className="relative">
                  <div
                    aria-hidden
                    className="absolute -inset-6 rounded-[36px] bg-gradient-to-br from-emerald/12 via-transparent to-cyan/12 blur-2xl"
                  />
                  <div className="device-frame relative">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={beat.image}
                      alt={beat.alt}
                      width={1200}
                      height={750}
                      className="w-full"
                      loading="lazy"
                    />
                  </div>
                </div>
              </Reveal>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
