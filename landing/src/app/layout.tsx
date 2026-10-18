import type { Metadata } from "next";
import { Syne, Outfit } from "next/font/google";
import "./globals.css";

const syne = Syne({
  subsets: ["latin"],
  variable: "--font-syne",
  weight: ["500", "600", "700", "800"],
});

const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-outfit",
  weight: ["300", "400", "500", "600", "700"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://ivdrive.eu"),
  title: {
    default: "iVDrive — EV telemetry for Škoda & VW Group",
    template: "%s — iVDrive",
  },
  description:
    "Open electric-vehicle telemetry for Škoda iV and VW Group: trips, charging curves, battery health, and analytics — self-hostable, community-driven.",
  icons: { icon: "/brand/logo.png" },
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://ivdrive.eu",
    siteName: "iVDrive",
    title: "iVDrive — EV telemetry for Škoda & VW Group",
    description:
      "Every charge. Every trip. Every percent. Open telemetry for Škoda iV & VW Group EVs.",
    images: [{ url: "/og.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "iVDrive — EV telemetry for Škoda & VW Group",
    description:
      "Every charge. Every trip. Every percent. Open telemetry for Škoda iV & VW Group EVs.",
    images: ["/og.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${syne.variable} ${outfit.variable}`}>
      <body>{children}</body>
    </html>
  );
}
