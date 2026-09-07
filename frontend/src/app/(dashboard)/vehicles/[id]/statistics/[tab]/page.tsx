import { ReactNode } from "react";
import { redirect } from "next/navigation";

interface PageProps {
  params: Promise<{ id: string; tab: string }>;
}

const VALID_TABS = [
  "car-overview",
  "trips",
  "movement",
  "driving-stats",
  "charging-stats",
  "charging-curve",
  "hvac-isolation",
  "climate-penalty",
  "charging-curve-integrals",
  "elevation",
  "speed-temp",
  "ice-vs-ev",
  "route-efficiency",
  "arrival-soc",
  "mileage",
  "battery-soh",
] as const;

type ValidTab = (typeof VALID_TABS)[number];

function isValidTab(tab: string): tab is ValidTab {
  return (VALID_TABS as readonly string[]).includes(tab);
}

export default async function VehicleStatisticsTabPage({ params }: PageProps): Promise<ReactNode> {
  const { id, tab } = await params;

  if (!isValidTab(tab)) {
    redirect(`/vehicles/${id}/statistics`);
  }

  // The actual tab rendering is handled by the client-side
  // StatisticsShell component, which reads the tab from the URL pathname.
  // This page exists purely to make Next.js accept the dynamic [tab] segment
  // and to redirect invalid tabs back to the default.
  const { StatisticsShell } = await import("@/components/statistics/StatisticsShell");
  return <StatisticsShell vehicleId={id} />;
}
