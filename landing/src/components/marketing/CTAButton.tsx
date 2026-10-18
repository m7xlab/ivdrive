import Link from "next/link";
import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { cn } from "@/lib/cn";

type Common = {
  children: ReactNode;
  className?: string;
};

function Inner({ children, className }: Common) {
  return (
    <span className={cn("relative z-10 inline-flex items-center gap-2", className)}>
      {children}
    </span>
  );
}

function isExternalAppRoute(href: string) {
  return href === "/login" || href === "/register" || href.startsWith("/login?") || href.startsWith("/register?");
}

export function CTAButton({
  href,
  children,
  variant = "primary",
  className,
  ...rest
}: Common & {
  href: string;
  variant?: "primary" | "ghost";
} & Omit<ComponentPropsWithoutRef<typeof Link>, "href" | "className" | "children">) {
  const classes = cn(variant === "primary" ? "btn-primary" : "btn-ghost", className);

  // Login/register live on the app (proxied), not in the static export — use <a> to avoid RSC prefetch 404s.
  if (isExternalAppRoute(href)) {
    return (
      <a href={href} className={classes}>
        <Inner>{children}</Inner>
      </a>
    );
  }

  return (
    <Link href={href} className={classes} {...rest}>
      <Inner>{children}</Inner>
    </Link>
  );
}

export function CTAAnchor({
  href,
  children,
  variant = "primary",
  className,
  ...rest
}: Common & {
  href: string;
  variant?: "primary" | "ghost";
} & Omit<ComponentPropsWithoutRef<"a">, "href" | "className" | "children">) {
  return (
    <a
      href={href}
      className={cn(variant === "primary" ? "btn-primary" : "btn-ghost", className)}
      {...rest}
    >
      <Inner>{children}</Inner>
    </a>
  );
}
