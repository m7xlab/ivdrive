"use client";

import { useState, useEffect } from "react";
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
    { id: "mileage", label: "Mileage" },
  ];

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
          <Tabs.List className="flex flex-nowrap gap-2 rounded-xl bg-iv-surface p-1.5 border border-iv-border w-full md:w-auto overflow-x-auto no-scrollbar">
            {TABS.map((t) => (
              <Tabs.Trigger
                key={t.id}
                value={t.id}
                className={cn(
                  "rounded-lg px-4 py-2 text-sm font-semibold transition-all",
                  activeTab === t.id
                    ? "bg-iv-charcoal text-iv-cyan shadow-sm border border-iv-border"
                    : "text-iv-text-muted hover:text-iv-text hover:bg-iv-charcoal/40"
                )}
              >
                {t.label}
              </Tabs.Trigger>
            ))}
          </Tabs.List>

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
          <Tabs.Content value="mileage">
            <MileageKMDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
        </div>
      </Tabs.Root>
    </div>
  );
}
