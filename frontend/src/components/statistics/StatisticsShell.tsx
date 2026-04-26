"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { subDays, startOfDay, endOfDay } from "date-fns";
import { cn } from "@/lib/cn";
import { DateRangePicker, type DateRangeValue } from "@/components/ui/DateRangePicker";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { PulseDashboard } from "./PulseDashboard";
import { EfficiencyDashboard } from "./EfficiencyDashboard";
import { CarOverviewDashboard } from "./CarOverviewDashboard";

import { TripsDashboard } from "./TripsDashboard";
import { MovementDashboard } from "./MovementDashboard";
import { DrivingStatisticsDashboard } from "./DrivingStatisticsDashboard";
import { ChargingStatisticsDashboard } from "./ChargingStatisticsDashboard";
import { MileageKMDashboard } from "./MileageKMDashboard";
import { ChargingAnalysisDashboard } from "./ChargingAnalysisDashboard";
import { HVACIsolationDashboard } from "./HVACIsolationDashboard";
import { ElevationPenaltyDashboard } from "./ElevationPenaltyDashboard";
import { SpeedTempMatrixDashboard } from "./SpeedTempMatrixDashboard";
import { VampireDrainDashboard } from "./VampireDrainDashboard";
import { IceTcoDashboard } from "./IceTcoDashboard";
import { RouteEfficiencyDashboard } from "./RouteEfficiencyDashboard";
import { PredictiveSocDashboard } from "./PredictiveSocDashboard";


export interface TimelineRange {
  from: Date;
  to: Date;
}

const TABS = [
  { id: "car-overview",        label: "Car Overview",       icon: "📊" },
  { id: "pulse",               label: "Live Pulse",         icon: "📡" },
  { id: "efficiency",          label: "Winter Penalty",      icon: "❄️" },
  { id: "trips",               label: "Trips",              icon: "🗺️" },
  { id: "movement",            label: "Movement",           icon: "🚗" },
  { id: "driving-stats",       label: "Driving Stats",       icon: "📈" },
  { id: "charging-stats",      label: "Charging Stats",     icon: "🔌" },
  { id: "charging-analysis", label: "Charging Analysis", icon: "⚡" },
  { id: "hvac-isolation",      label: "HVAC Isolation",     icon: "🌡️" },
  { id: "elevation-penalty",   label: "Elevation",         icon: "⛰️" },
  { id: "speed-temp-matrix",   label: "Speed × Temp",       icon: "🌡️" },
  { id: "vampire-drain",       label: "Vampire Drain",       icon: "🧛" },
  { id: "ice-tco",             label: "ICE vs EV",           icon: "⛽" },
  { id: "route-efficiency",    label: "Route Efficiency",   icon: "🛣️" },
  { id: "predictive-soc",      label: "Arrival SoC",         icon: "🎯" },
  { id: "mileage",             label: "Mileage",             icon: "📍" },
] as const;

const TAB_MIN_WIDTH = 120; // px, min width per tab button
const TAB_GAP = 8;         // px gap between tabs

export function StatisticsShell({ vehicleId }: { vehicleId: string }) {
  const [activeTab, setActiveTab] = useState<string>("car-overview");
  const [dateRange, setDateRange] = useState<DateRangeValue | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const now = new Date();
    setDateRange({ from: startOfDay(subDays(now, 7)), to: endOfDay(now) });
  }, []);

  const scrollIntoView = useCallback((tabId: string) => {
    const el = scrollRef.current;
    if (!el) return;
    const idx = TABS.findIndex(t => t.id === tabId);
    if (idx < 0) return;
    const tabWidth = TAB_MIN_WIDTH + TAB_GAP;
    const scrollTarget = idx * tabWidth - el.clientWidth / 2 + tabWidth / 2;
    el.scrollTo({ left: Math.max(0, scrollTarget), behavior: "smooth" });
  }, []);

  const navigate = useCallback((dir: -1 | 1) => {
    const idx = TABS.findIndex(t => t.id === activeTab);
    const next = Math.max(0, Math.min(TABS.length - 1, idx + dir));
    setActiveTab(TABS[next].id);
  }, [activeTab]);

  useEffect(() => {
    // When activeTab changes externally (click), scroll it into view
    scrollIntoView(activeTab);
  }, [activeTab, scrollIntoView]);

  // Keyboard left/right navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") navigate(1);
      if (e.key === "ArrowLeft")  navigate(-1);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [navigate]);

  if (!dateRange) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-center py-24">
          <div className="text-iv-muted text-sm">Loading period…</div>
        </div>
      </div>
    );
  }

  const range: TimelineRange = { from: dateRange.from, to: dateRange.to };
  const activeIdx = TABS.findIndex(t => t.id === activeTab);

  return (
    <div className="space-y-6">
      {/* ── Tab Navigation Card ── */}
      <div className="glass rounded-2xl border border-iv-border p-3">
        <div className="flex items-center gap-2">
          {/* Left arrow */}
          <button
            onClick={() => navigate(-1)}
            disabled={activeIdx === 0}
            className="shrink-0 flex items-center justify-center w-10 h-10 rounded-xl border border-iv-border text-iv-muted hover:text-iv-text hover:bg-iv-charcoal transition-all disabled:opacity-20 disabled:cursor-not-allowed"
            aria-label="Previous tab"
          >
            <ChevronLeft size={18} />
          </button>

          {/* Tab strip */}
          <div
            ref={scrollRef}
            className="flex flex-1 gap-2 overflow-x-auto no-scrollbar scroll-smooth snap-x snap-mandatory"
            style={{ paddingBottom: "2px" }}
          >
            {TABS.map((t, i) => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={cn(
                  "shrink-0 snap-start rounded-xl px-4 py-2.5 text-[13px] font-semibold transition-all flex items-center gap-2 border",
                  activeTab === t.id
                    ? "bg-iv-charcoal text-iv-cyan border-iv-border shadow-sm"
                    : "bg-iv-surface text-iv-text-muted border-transparent hover:border-iv-border/60 hover:text-iv-text"
                )}
                style={{ minWidth: `${TAB_MIN_WIDTH}px` }}
              >
                <span className="text-base">{t.icon}</span>
                <span>{t.label}</span>
              </button>
            ))}
          </div>

          {/* Right arrow */}
          <button
            onClick={() => navigate(1)}
            disabled={activeIdx === TABS.length - 1}
            className="shrink-0 flex items-center justify-center w-10 h-10 rounded-xl border border-iv-border text-iv-muted hover:text-iv-text hover:bg-iv-charcoal transition-all disabled:opacity-20 disabled:cursor-not-allowed"
            aria-label="Next tab"
          >
            <ChevronRight size={18} />
          </button>
        </div>

        {/* Dot indicators */}
        <div className="flex justify-center gap-1.5 mt-2">
          {TABS.map((t, i) => (
            <button
              key={t.id}
              onClick={() => { setActiveTab(t.id); scrollIntoView(t.id); }}
              className={cn(
                "rounded-full transition-all",
                activeTab === t.id ? "w-5 h-2 bg-iv-cyan" : "w-2 h-2 bg-iv-border hover:bg-iv-text-muted"
              )}
              aria-label={`Go to ${t.label}`}
            />
          ))}
        </div>
      </div>

      {/* Period picker */}
      <div className="flex items-center gap-3">
        <span className="text-xs font-medium text-iv-text-muted uppercase tracking-wider whitespace-nowrap hidden sm:inline-block">
          Period
        </span>
        <DateRangePicker value={dateRange} onChange={setDateRange} />
      </div>

      {/* ── Content ── */}
      <div className="animate-in fade-in duration-300">
        <Tabs.Root value={activeTab} onValueChange={setActiveTab}>
          <Tabs.Content value="car-overview">
            <CarOverviewDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="pulse">
            <PulseDashboard vehicleId={vehicleId} />
          </Tabs.Content>
          <Tabs.Content value="efficiency">
            <EfficiencyDashboard vehicleId={vehicleId} dateRange={range} />
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
          <Tabs.Content value="charging-analysis">
            <ChargingAnalysisDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="hvac-isolation">
            <HVACIsolationDashboard vehicleId={vehicleId} dateRange={range} />
          </Tabs.Content>
          <Tabs.Content value="elevation-penalty">
            <ElevationPenaltyDashboard vehicleId={vehicleId} />
          </Tabs.Content>
          <Tabs.Content value="speed-temp-matrix">
            <SpeedTempMatrixDashboard vehicleId={vehicleId} />
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
        </Tabs.Root>
      </div>
    </div>
  );
}