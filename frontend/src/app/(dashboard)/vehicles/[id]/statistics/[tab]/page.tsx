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
  "elevation-penalty",
  "speed-temp-matrix",
  "ice-tco",
  "route-efficiency",
  "predictive-soc",
  "mileage",
  "battery-soh",
] as const;

const TAB_ALIASES: Record<string, string> = {
  elevation: "elevation-penalty",
  "speed-temp": "speed-temp-matrix",
  "ice-vs-ev": "ice-tco",
  "arrival-soc": "predictive-soc",
};

export default async function VehicleStatisticsTabPage({ params }: PageProps): Promise<ReactNode> {
  const { id, tab } = await params;
  const canonical = TAB_ALIASES[tab] ?? tab;

  if (!(VALID_TABS as readonly string[]).includes(canonical)) {
    redirect(`/vehicles/${id}/statistics`);
  }

  if (canonical !== tab) {
    redirect(`/vehicles/${id}/statistics/${canonical}`);
  }

  const { StatisticsShell } = await import("@/components/statistics/StatisticsShell");
  return <StatisticsShell vehicleId={id} initialTab={canonical} />;
}
