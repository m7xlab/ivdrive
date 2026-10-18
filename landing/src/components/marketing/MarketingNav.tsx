"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Menu, X, ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/cn";
import { CTAButton } from "./CTAButton";

const links = [
  { href: "/features/", label: "Features" },
  { href: "/roadmap/", label: "Roadmap" },
  { href: "/open-source/", label: "Open Source" },
  { href: "/community/", label: "Community" },
  { href: "/sponsors/", label: "Sponsors" },
  { href: "/about/", label: "About" },
];

export function MarketingNav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-all duration-500",
        scrolled
          ? "border-b border-white/5 bg-[#05070f]/75 backdrop-blur-xl"
          : "border-b border-transparent bg-transparent",
      )}
    >
      <div className="container-x flex h-[72px] items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/brand/logo.png"
            alt="iVDrive"
            width={36}
            height={36}
            className="rounded-[10px] shadow-[0_0_24px_rgba(75,168,46,0.35)]"
          />
          <span className="font-display text-[1.15rem] font-semibold tracking-tight">
            <span className="text-gradient">iV</span>
            <span className="text-ink">Drive</span>
          </span>
        </Link>

        <nav className="hidden items-center gap-8 md:flex">
          {links.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-[0.92rem] text-muted transition-colors hover:text-ink"
            >
              {item.label}
            </Link>
          ))}
          <a
            href="/docs/"
            className="inline-flex items-center gap-1 text-[0.92rem] text-muted transition-colors hover:text-cyan"
          >
            Docs
            <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <a
            href="/login"
            className="px-3 py-2 text-[0.92rem] text-muted transition-colors hover:text-ink"
          >
            Sign in
          </a>
          <CTAButton href="/register" className="!px-5 !py-2.5 text-sm">
            Request invite
          </CTAButton>
        </div>

        <button
          type="button"
          className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/10 text-ink md:hidden"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? "Close menu" : "Open menu"}
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {open && (
        <div className="border-t border-white/5 bg-[#05070f]/95 px-5 pb-6 pt-2 backdrop-blur-xl md:hidden">
          <div className="flex flex-col gap-1">
            {links.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className="rounded-xl px-3 py-3 text-ink hover:bg-white/5"
              >
                {item.label}
              </Link>
            ))}
            <a
              href="/docs/"
              className="rounded-xl px-3 py-3 text-ink hover:bg-white/5"
            >
              Docs
            </a>
            <div className="mt-3 flex flex-col gap-2">
              <a
                href="/login"
                onClick={() => setOpen(false)}
                className="btn-ghost w-full"
              >
                Sign in
              </a>
              <CTAButton href="/register" className="w-full" onClick={() => setOpen(false)}>
                Request invite
              </CTAButton>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
