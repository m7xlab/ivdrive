import { RevealGroup, RevealItem } from "./Reveal";

const models = [
  "Enyaq iV",
  "Enyaq Coupé iV",
  "Enyaq RS",
  "Elroq",
  "More Škoda EVs",
];

export function TrustBar() {
  return (
    <section className="relative border-y border-white/[0.06] py-10">
      <div className="container-x">
        <RevealGroup className="flex flex-col items-center gap-6 md:flex-row md:justify-between">
          <RevealItem>
            <p className="text-[0.78rem] font-semibold uppercase tracking-[0.2em] text-faint">
              Built for Škoda fully electric
            </p>
          </RevealItem>
          <RevealItem className="w-full md:w-auto">
            <div className="flex flex-wrap items-center justify-center gap-2.5 md:justify-end">
              {models.map((m) => (
                <span
                  key={m}
                  className="rounded-full border border-white/[0.08] bg-white/[0.03] px-3.5 py-1.5 text-[0.82rem] text-muted"
                >
                  {m}
                </span>
              ))}
            </div>
          </RevealItem>
        </RevealGroup>
      </div>
    </section>
  );
}
