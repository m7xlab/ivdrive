"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { subDays, startOfDay, endOfDay } from "date-fns";
import { cn } from "@/lib/cn";
import { DateRangePicker, type DateRangeValue } from "@/components/ui/DateRangePicker";

import { PulseDashboard } from "./PulseDashboard";
import { EfficiencyDashboard } from "./EfficiencyDashboard";
import { ChargingCostsDashboard } from "./ChargingCostsDashboard";
import { CarOverviewDashboard } from "./CarOverviewDashboard";

import { TripsDashboard } from "./TripsDashboard";
import { MovementDashboard } from "./MovementDashboard";
import { DrivingStatisticsDashboard } from "./DrivingStatisticsDashboard";
import { ChargingStatisticsDashboard } from "./ChargingStatisticsDashboard";
import { MileageKMDashboard } from "./MileageKMDashboard";
import { ChargingCurveDashboard } from "./ChargingCurveDashboard";
import { HVACIsolationDashboard } from "./HVACIsolationDashboard";
import { ChargingCurveIntegralsDashboard } from "./ChargingCurveIntegralsDashboard";
import { ElevationPenaltyDashboard } from "./ElevationPenaltyDashboard";
import { SpeedTempMatrixDashboard } from "./SpeedTempMatrixDashboard";
import { MissedSavingsDashboard } from "./MissedSavingsDashboard";
import { VampireDrainDashboard } from "./VampireDrainDashboard";
import { IceTcoDashboard } from "./IceTcoDashboard";
import { RouteEfficiencyDashboard } from "./RouteEfficiencyDashboard";
import { PredictiveSocDashboard } from "./PredictiveSocDashboard";


export interface TimelineRange {
  from: Date;
  to: Date;
}

export function StatisticsShell({ vehicleId }: { vehicleId: string }) {
  const [activeTab, setActiveTab] = useState("car-overview");

  // Avoid hydration mismatch (#418): server and client must render the same initial state.
  // new Date() differs between server and client, so we set the real range only in useEffect.
  const [dateRange, setDateRange] = useState<DateRangeValue | null>(null);

  useEffect(() => {
    const now = new Date();
    setDateRange({
      from: startOfDay(subDays(now, 7)),
      to: endOfDay(now),
    });
  }, []);

  const TABS = [
    { id: "car-overview", label: "Car Overview" },
    { id: "pulse", label: "Live Pulse" },
    { id: "efficiency", label: "Winter Penalty" },
    { id: "economics", label: "Charging Economics" },
    { id: "trips", label: "Trips" },
    { id: "movement", label: "Movement" },
    { id: "driving-stats", label: "Driving Stats" },
    { id: "charging-stats", label: "Charging Stats" },
    { id: "charging-curve", label: "Charging Curve" },
    { id: "hvac-isolation", label: "HVAC Isolation" },
    { id: "charging-curve-integrals", label: "Curve Int." },
    { id: "elevation-penalty", label: "Elevation" },
    { id: "speed-temp-matrix", label: "Speed × Temp" },
    { id: "missed-savings", label: "Charge Windows" },
    { id: "vampire-drain", label: "Vampire Drain" },
    { id: "ice-tco", label: "ICE vs EV" },
    { id: "route-efficiency", label: "Route Efficiency" },
    { id: "predictive-soc", label: "Arrival SoC" },
    { id: "mileage", label: "Mileage" },
  ];

  const tabListRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const updateScrollArrows = useCallback(() => {
    const el = tabListRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 8);
    setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 8);
  }, []);

  useEffect(() => {
    updateScrollArrows();
    const el = tabListRef.current;
    el?.addEventListener("scroll", updateScrollArrows, { passive: true });
    window.addEventListener("resize", updateScrollArrows);
    return () => {
      el?.removeEventListener("scroll", updateScrollArrows);
      window.removeEventListener("resize", updateScrollArrows);
    };
  }, [updateScrollArrows]);

  const scrollBy = (dir: -1 | 1) => {
    tabListRef.current?.scrollBy({ left: dir * 200, behavior: "smooth" });
  };

  // Keyboard arrow navigation for desktop
  const handleTabKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowRight") { e.preventDefault(); scrollBy(1); }
    if (e.key === "ArrowLeft") { e.preventDefault(); scrollBy(-1); }
  };

  if (!dateRange) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-center py-24">
          <div className="text-iv-muted text-sm">Loading period…</div>
        </div>
      </div>
    );
  }

  const range: TimelineRange = {
    from: dateRange.from,
    to: dateRange.to,
  };

  return (
    <div className="space-y-6">
      <Tabs.Root value={activeTab} onValueChange={setActiveTab}>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
          <div className="relative flex items-center gap-1">
            {canScrollLeft && (
              <button
                onClick={() => scrollBy(-1)}
                className="shrink-0 rounded-lg px-1.5 py-2 text-sm text-iv-muted hover:text-iv-text hover:bg-iv-surface border border-iv-border transition-all"
                aria-label="Scroll tabs left"
              >
                ‹
              </button>
            )}
            <Tabs.List
              ref={tabListRef}
              onKeyDown={handleTabKeyDown}
              className="flex flex-nowrap gap-1.5 rounded-xl bg-iv-surface p-1.5 border border-iv-border w-full md:w-auto overflow-x-auto no-scrollbar scroll-smooth"
              style={{ scrollPaddingLeft: "0.5rem", scrollPaddingRight: "0.5rem" }}
            >
              {TABS.map((t) => (
                <Tabs.Trigger
                  key={t.id}
                  value={t.id}
                  className={cn(
                    "rounded-lg px-3 py-2 text-[13px] font-semibold transition-all shrink-0 whitespace-nowrap",
                    activeTab === t.id
                      ? "bg-iv-charcoal text-iv-cyan shadow-sm border border-iv-border"
                      : "text-iv-text-muted hover:text-iv-text hover:bg-iv-charcoal/40 border border-transparent hover:border-iv-border/50"
                  )}
                >
                  {t.label}
                </Tabs.Trigger>
              ))}
            </Tabs.List>
            {canScrollRight && (
              <button
                onClick={() => scrollBy(1)}
                className="shrink-0 rounded-lg px-1.5 py-2 text-sm text-iv-muted hover:text-iv-text hover:bg-iv-surface border border-iv-border transition-all"
                aria-label="Scroll tabs right"
              >
                ›
              </button>
            )}
          </div>

          <div className="flex items-center gap-3 justify-center md:justify-start self-start md:self-auto">
            <span className="text-xs font-medium text-iv-text-muted uppercase tracking-wider whitespace-nowrap hidden sm:inline-block">
              Period
            </span>
            <DateRangePicker value={dateRange} onChange={setDateRange} />
          </div>
        </div>

        <div className="animate-in fade-in duration-500">
          <Tabs.Content value="car-overview">
            <CarOverviewDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="pulse">
            <PulseDashboard vehicleId={vehicleId} />
          </Tabs.Content>
          <Tabs.Content value="efficiency">
            <EfficiencyDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="economics">
            <ChargingCostsDashboard vehicleId={vehicleId} dateRange={range} />
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
          <Tabs.Content value="charging-curve-integrals">
            <ChargingCurveIntegralsDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="elevation-penalty">
            <ElevationPenaltyDashboard vehicleId={vehicleId} />
          </Tabs.Content>
          <Tabs.Content value="speed-temp-matrix">
            <SpeedTempMatrixDashboard vehicleId={vehicleId} />
          </Tabs.Content>
          <Tabs.Content value="missed-savings">
            <MissedSavingsDashboard vehicleId={vehicleId} />
          </Tabs.Content>
          <Tabs.Content value="vampire-drain">
            <VampireDrainDashboard vehicleId={vehicleId} />
          </Tabs.Content>
          <Tabs.Content value="ice-tco">
            <IceTcoDashboard vehicleId={vehicleId} />
          </Tabs.Content>
          <Tabs.Content value="route-efficiency">
            <RouteEfficiencyDashboard vehicleId={vehicleId} />
          </Tabs.Content>
          <Tabs.Content value="predictive-soc">
            <PredictiveSocDashboard vehicleId={vehicleId} />
          </Tabs.Content>
          <Tabs.Content value="mileage">
            <MileageKMDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
        </div>
      </Tabs.Root>
    </div>
  );
}
