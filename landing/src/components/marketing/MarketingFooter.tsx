import Link from "next/link";
import { ArrowUpRight, Github } from "lucide-react";

const cols = [
  {
    title: "Product",
    links: [
      { href: "/features/", label: "Features" },
      { href: "/roadmap/", label: "Roadmap" },
      { href: "/open-source/", label: "Open source" },
      { href: "/sponsors/", label: "Sponsors" },
      { href: "/about/", label: "About" },
    ],
  },
  {
    title: "Get started",
    links: [
      { href: "https://app.ivdrive.eu/register", label: "Request invite" },
      { href: "https://app.ivdrive.eu/login", label: "Sign in" },
      { href: "/docs/", label: "Documentation" },
    ],
  },
  {
    title: "Project",
    links: [
      {
        href: "https://github.com/m7xlab/iVDrive",
        label: "GitHub",
        external: true,
      },
      {
        href: "https://github.com/m7xlab/iVDrive/blob/main/CONTRIBUTING.md",
        label: "Contributing",
        external: true,
      },
      {
        href: "https://github.com/m7xlab/iVDrive/blob/main/ROADMAP.md",
        label: "Roadmap",
        external: true,
      },
    ],
  },
];

export function MarketingFooter() {
  return (
    <footer className="relative border-t border-white/5 bg-void">
      <div className="container-x py-16">
        <div className="grid gap-12 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div>
            <Link href="/" className="flex items-center gap-2.5">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/brand/logo.png" alt="iVDrive" width={32} height={32} className="rounded-lg" />
              <span className="font-display text-lg font-semibold">
                <span className="text-gradient">iV</span>Drive
              </span>
            </Link>
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-muted">
              Open electric-vehicle telemetry for Škoda iV and the wider VW Group.
              Your data. Your server. Your insights.
            </p>
            <a
              href="https://github.com/m7xlab/iVDrive"
              target="_blank"
              rel="noopener noreferrer"
              className="mt-5 inline-flex items-center gap-2 text-sm text-muted transition-colors hover:text-cyan"
            >
              <Github className="h-4 w-4" />
              github.com/m7xlab/iVDrive
            </a>
          </div>

          {cols.map((col) => (
            <div key={col.title}>
              <h3 className="text-[0.78rem] font-semibold uppercase tracking-[0.18em] text-faint">
                {col.title}
              </h3>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((link) => (
                  <li key={link.label}>
                    {"external" in link && link.external ? (
                      <a
                        href={link.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-sm text-muted transition-colors hover:text-ink"
                      >
                        {link.label}
                        <ArrowUpRight className="h-3.5 w-3.5" />
                      </a>
                    ) : link.href === "https://app.ivdrive.eu/login" || link.href === "https://app.ivdrive.eu/register" ? (
                      <a
                        href={link.href}
                        className="text-sm text-muted transition-colors hover:text-ink"
                      >
                        {link.label}
                      </a>
                    ) : (
                      <Link
                        href={link.href}
                        className="text-sm text-muted transition-colors hover:text-ink"
                      >
                        {link.label}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-14 flex flex-col gap-3 border-t border-white/5 pt-6 text-xs text-faint sm:flex-row sm:items-center sm:justify-between">
          <p>© {new Date().getFullYear()} iVDrive · Elastic License 2.0 (ELv2)</p>
          <p>Community-driven · Self-hostable · Built for VW Group EVs</p>
        </div>
      </div>
    </footer>
  );
}
