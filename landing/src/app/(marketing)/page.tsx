import type { Metadata } from "next";
import { Hero } from "@/components/marketing/Hero";
import { TrustBar } from "@/components/marketing/TrustBar";
import { FeatureGrid } from "@/components/marketing/FeatureGrid";
import { StickyShowcase } from "@/components/marketing/StickyShowcase";
import { OpenSourceSection } from "@/components/marketing/OpenSourceSection";
import { CommunitySection } from "@/components/marketing/CommunitySection";
import { BetaCTA } from "@/components/marketing/BetaCTA";

export const metadata: Metadata = {
  title: "iVDrive — EV telemetry for Škoda & VW Group",
  description:
    "Every charge. Every trip. Every percent. Open EV telemetry for Škoda iV and VW Group — trips, charging curves, battery health, self-hostable.",
  alternates: { canonical: "https://ivdrive.eu/" },
};

export default function HomePage() {
  return (
    <>
      <Hero />
      <TrustBar />
      <FeatureGrid />
      <StickyShowcase />
      <OpenSourceSection />
      <CommunitySection />
      <BetaCTA />
    </>
  );
}
