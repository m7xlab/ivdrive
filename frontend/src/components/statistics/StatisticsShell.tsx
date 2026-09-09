"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as Tabs from "@radix-ui/react-tabs";
import { subDays, startOfDay, endOfDay } from "date-fns";
import { ArrowLeft } from "lucide-react";
import { cn } from "@/lib/cn";
import { DateRangePicker, type DateRangeValue } from "@/components/ui/DateRangePicker";

import { CarOverviewDashboard } from "./CarOverviewDashboard";
import { TripsDashboard } from "./TripsDashboard";
import { MovementDashboard } from "./MovementDashboard";
import { DrivingStatisticsDashboard } from "./DrivingStatisticsDashboard";
import { ChargingStatisticsDashboard } from "./ChargingStatisticsDashboard";
import { MileageKMDashboard } from "./MileageKMDashboard";
import { ChargingCurveDashboard } from "./ChargingCurveDashboard";
import { HVACIsolationDashboard } from "./HVACIsolationDashboard";
import { ClimatePenaltyDashboard } from "./ClimatePenaltyDashboard";
import { ChargingCurveIntegralsDashboard } from "./ChargingCurveIntegralsDashboard";
import { ElevationPenaltyDashboard } from "./ElevationPenaltyDashboard";
import { SpeedTempMatrixDashboard } from "./SpeedTempMatrixDashboard";
import { BatterySoHDashboard } from "./BatterySoHDashboard";
import { IceTcoDashboard } from "./IceTcoDashboard";
import { RouteEfficiencyDashboard } from "./RouteEfficiencyDashboard";
import { PredictiveSocDashboard } from "./PredictiveSocDashboard";

export interface TimelineRange {
  from: Date;
  to: Date;
}

type TabDef = { id: string; label: string; icon: string };

const TAB_GROUPS: { id: string; label: string; hint: string; tabs: TabDef[] }[] = [
  {
    id: "daily",
    label: "Daily",
    hint: "What you check after a drive",
    tabs: [
      { id: "car-overview", label: "Car Overview", icon: "📊" },
      { id: "trips", label: "Trips", icon: "🗺️" },
      { id: "movement", label: "Movement", icon: "🚗" },
      { id: "driving-stats", label: "Driving Stats", icon: "📈" },
      { id: "charging-stats", label: "Charging Stats", icon: "🔌" },
      { id: "mileage", label: "Mileage", icon: "📍" },
      { id: "battery-soh", label: "Battery SoH", icon: "🔋" },
      { id: "predictive-soc", label: "Arrival SoC", icon: "🎯" },
    ],
  },
  {
    id: "analysis",
    label: "Analysis",
    hint: "Deeper breakdowns",
    tabs: [
      { id: "charging-curve", label: "Charging Curve", icon: "📉" },
      { id: "charging-curve-integrals", label: "Curve Int.", icon: "🔋" },
      { id: "hvac-isolation", label: "HVAC Isolation", icon: "🌡️" },
      { id: "climate-penalty", label: "Climate Penalty", icon: "❄️" },
      { id: "elevation-penalty", label: "Elevation", icon: "⛰️" },
      { id: "speed-temp-matrix", label: "Speed × Temp", icon: "🌡️" },
      { id: "ice-tco", label: "ICE vs EV", icon: "⛽" },
      { id: "route-efficiency", label: "Route Efficiency", icon: "🛣️" },
    ],
  },
];

const ALL_TABS = TAB_GROUPS.flatMap((g) => g.tabs);

function isKnownTab(tab: string | undefined): tab is string {
  return !!tab && ALL_TABS.some((t) => t.id === tab);
}

export function StatisticsShell({
  vehicleId,
  initialTab,
}: {
  vehicleId: string;
  initialTab?: string;
}) {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<string>(
    isKnownTab(initialTab) ? initialTab : "car-overview",
  );
  const [dateRange, setDateRange] = useState<DateRangeValue | null>(null);

  useEffect(() => {
    const now = new Date();
    setDateRange({ from: startOfDay(subDays(now, 7)), to: endOfDay(now) });
  }, []);

  useEffect(() => {
    if (isKnownTab(initialTab)) {
      setActiveTab(initialTab);
    }
  }, [initialTab]);

  const selectTab = useCallback(
    (tabId: string) => {
      if (!isKnownTab(tabId) || tabId === activeTab) return;
      setActiveTab(tabId);
      router.replace(`/vehicles/${vehicleId}/statistics/${tabId}`, { scroll: false });
    },
    [activeTab, router, vehicleId],
  );

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const idx = ALL_TABS.findIndex((t) => t.id === activeTab);
      if (e.key === "ArrowRight" && idx < ALL_TABS.length - 1) selectTab(ALL_TABS[idx + 1].id);
      if (e.key === "ArrowLeft" && idx > 0) selectTab(ALL_TABS[idx - 1].id);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activeTab, selectTab]);

  const activeLabel = useMemo(
    () => ALL_TABS.find((t) => t.id === activeTab)?.label ?? "Advanced",
    [activeTab],
  );

  if (!dateRange) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 overflow-x-hidden">
        <div className="flex items-center justify-center py-24">
          <div className="text-iv-muted text-sm">Loading period…</div>
        </div>
      </div>
    );
  }

  const range: TimelineRange = { from: dateRange.from, to: dateRange.to };

  return (
    <div className="mx-auto max-w-6xl space-y-6 overflow-x-hidden">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          href={`/vehicles/${vehicleId}`}
          className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border border-iv-border bg-iv-surface text-iv-muted transition-colors hover:text-iv-text hover:border-iv-green/40"
          aria-label="Back to vehicle"
        >
          <ArrowLeft size={18} />
        </Link>
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wider text-iv-muted">Advanced statistics</p>
          <h1 className="text-lg font-semibold text-iv-text truncate">{activeLabel}</h1>
        </div>
      </div>

      <div className="glass rounded-2xl border border-iv-border p-3 sm:p-4 space-y-4">
        {TAB_GROUPS.map((group) => (
          <div key={group.id}>
            <div className="mb-2 flex items-baseline gap-2 px-0.5">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-iv-muted">
                {group.label}
              </p>
              <p className="hidden sm:block text-[10px] text-iv-muted/60">{group.hint}</p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {group.tabs.map((t) => {
                const selected = activeTab === t.id;
                return (
                  <button
                    type="button"
                    key={t.id}
                    onClick={() => selectTab(t.id)}
                    aria-current={selected ? "page" : undefined}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium border transition-colors",
                      selected
                        ? "bg-iv-cyan/12 text-iv-cyan border-iv-cyan/35"
                        : "bg-iv-surface text-iv-muted border-transparent hover:border-iv-border hover:text-iv-text",
                    )}
                  >
                    <span className="text-sm leading-none" aria-hidden>
                      {t.icon}
                    </span>
                    <span>{t.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <span className="text-xs font-medium text-iv-text-muted uppercase tracking-wider whitespace-nowrap hidden sm:inline-block">
          Period
        </span>
        <DateRangePicker value={dateRange} onChange={setDateRange} />
      </div>

      <div className="animate-in fade-in duration-300">
        <Tabs.Root value={activeTab} onValueChange={selectTab}>
          <Tabs.Content value="car-overview">
            <CarOverviewDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="trips">
            <TripsDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="movement">
            <MovementDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="driving-stats">
            <DrivingStatisticsDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="charging-stats">
            <ChargingStatisticsDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="charging-curve">
            <ChargingCurveDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="hvac-isolation">
            <HVACIsolationDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="climate-penalty">
            <ClimatePenaltyDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="charging-curve-integrals">
            <ChargingCurveIntegralsDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="elevation-penalty">
            <ElevationPenaltyDashboard vehicleId={vehicleId} dateRange={dateRange} />
          </Tabs.Content>
          <Tabs.Content value="speed-temp-matrix">
            <SpeedTempMatrixDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="ice-tco">
            <IceTcoDashboard vehicleId={vehicleId} dateRange={dateRange} />
          </Tabs.Content>
          <Tabs.Content value="route-efficiency">
            <RouteEfficiencyDashboard vehicleId={vehicleId} dateRange={dateRange} />
          </Tabs.Content>
          <Tabs.Content value="predictive-soc">
            <PredictiveSocDashboard vehicleId={vehicleId} dateRange={dateRange} />
          </Tabs.Content>
          <Tabs.Content value="mileage">
            <MileageKMDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="battery-soh">
            <BatterySoHDashboard vehicleId={vehicleId} dateRange={dateRange} />
          </Tabs.Content>
        </Tabs.Root>
      </div>
    </div>
  );
}
