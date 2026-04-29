"use client";

import { useEffect, useState, useCallback } from "react";
import { format, parseISO } from "date-fns";
import { Loader2, Route, Zap, BatteryCharging, Timer, Calendar, History } from "lucide-react";
import { api } from "@/lib/api";
import type { TimelineRange } from "./StatisticsShell";
import { formatSmartDuration } from "@/lib/format";

export interface DrivingStatisticsDashboardProps {
  vehicleId: string;
  dateRange: TimelineRange;
  period?: "day" | "week" | "month" | "year";
}

interface StatisticsRow {
  period: string;
  drives_count: number;
  total_distance_km: number;
  time_driven_seconds: number;
  median_distance_km: number | null;
  charging_sessions_count: number;
  total_energy_kwh: number;
  total_kwh_consumed: number;
  time_charging_seconds: number;
}

function formatDuration(seconds: number): string {
  if (seconds <= 0 || !Number.isFinite(seconds)) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${Math.round(seconds)}s`;
}

function formatPeriodLabel(iso: string, period: string): string {
  try {
    const d = parseISO(iso.replace("Z", "+00:00"));
    switch (period) {
      case "year":
        return format(d, "yyyy");
      case "month":
        return format(d, "MMM yyyy");
      case "week":
        return `Week ${format(d, "I, MMM d")}`;
      default:
        return format(d, "MMMM d, yyyy");
    }
  } catch {
    return iso;
  }
}

export function DrivingStatisticsDashboard({
  vehicleId,
  dateRange,
  period = "day",
}: DrivingStatisticsDashboardProps) {
  const [rows, setRows] = useState<StatisticsRow[]>([]);
  const [loading, setLoading] = useState(true);

  const fromISO = dateRange.from.toISOString();
  const toISO = dateRange.to.toISOString();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.getStatistics(vehicleId, period, 30, fromISO, toISO);
      setRows(list ?? []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [vehicleId, period, fromISO, toISO]);

  useEffect(() => {
    fetchData();
    const isLive = !toISO || new Date(toISO) >= new Date();
    if (!isLive) return;

    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData, toISO]);

  const latestData = rows.length > 0 ? rows[0] : null;
  const historicalData = rows.length > 1 ? rows.slice(1) : [];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-iv-muted" />
      </div>
    );
  }

  if (!latestData) {
    return (
      <div className="py-24 text-center text-sm text-iv-muted">
        No data for the selected period.
      </div>
    );
  }

  const latestStats = [
    {
      label: "Distance",
      value: `${latestData.total_distance_km.toFixed(1)} km`,
      subValue: `${latestData.drives_count} drives`,
      icon: Route,
      color: "cyan",
    },
    {
      label: "Energy Used",
      value: `${latestData.total_kwh_consumed.toFixed(2)} kWh`,
      subValue: `${formatDuration(latestData.time_driven_seconds)} driven`,
      icon: Zap,
      color: "green",
    },
    {
      label: "Energy Charged",
      value: `${latestData.total_energy_kwh.toFixed(2)} kWh`,
      subValue: `${latestData.charging_sessions_count} charges`,
      icon: BatteryCharging,
      color: "blue",
    },
    {
      label: "Time Charging",
      value: formatDuration(latestData.time_charging_seconds),
      subValue: <>&nbsp;</>,
      icon: Timer,
      color: "yellow",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Latest Day's Statistics */}
      <div className="glass rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-iv-text">
                {formatPeriodLabel(latestData.period, period)}
            </h3>
            <span className="text-xs bg-iv-surface border border-iv-border text-iv-muted px-2 py-0.5 rounded-full">
                Latest
            </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {latestStats.map((stat) => (
            <div
              key={stat.label}
              className={`bg-iv-surface/60 rounded-xl p-4 border border-iv-border space-y-2`}
            >
              <div className="flex items-center gap-2">
                <stat.icon size={16} className={`text-iv-${stat.color}`} />
                <span className="text-xs font-semibold text-iv-muted uppercase tracking-wide">
                  {stat.label}
                </span>
              </div>
              <p className={`text-2xl font-bold text-iv-text`}>{stat.value}</p>
              <p className="text-xs text-iv-muted">{stat.subValue}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Historical Data */}
      {historicalData.length > 0 && (
        <div className="glass rounded-xl p-5 space-y-3">
            <h3 className="text-sm font-semibold text-iv-text flex items-center gap-2">
                <History size={14}/>
                Historical Data
            </h3>
            <div className="space-y-2">
                {historicalData.map((item) => (
                <div key={item.period} className="flex items-center gap-3 p-3 rounded-xl bg-iv-surface/60 border-iv-border/50">
                    <div className="p-2 rounded-full shrink-0 bg-iv-cyan/10">
                        <Calendar size={14} className="text-iv-cyan" />
                    </div>
                    <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1">
                        <div className="flex flex-col items-start min-w-0">
                            <p className="text-xs text-iv-muted">Period</p>
                            <p className="text-sm font-medium text-iv-text truncate">{formatPeriodLabel(item.period, period)}</p>
                        </div>
                        <div className="flex flex-col items-start min-w-0">
                            <p className="text-xs text-iv-muted">Distance</p>
                            <p className="text-sm font-medium text-iv-text">{item.total_distance_km.toFixed(1)} km</p>
                        </div>
                        <div className="flex flex-col items-start min-w-0">
                            <p className="text-xs text-iv-muted">Energy Used</p>
                            <p className="text-sm font-medium text-iv-text">{item.total_kwh_consumed.toFixed(2)} kWh</p>
                        </div>
                        <div className="flex flex-col items-start min-w-0">
                            <p className="text-xs text-iv-muted">Time Driven</p>
                            <p className="text-sm font-medium text-iv-text">{formatDuration(item.time_driven_seconds)}</p>
                        </div>
                    </div>
                </div>
                ))}
            </div>
        </div>
      )}
    </div>
  );
}
