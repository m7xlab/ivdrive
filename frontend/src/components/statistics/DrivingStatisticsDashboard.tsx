"use client";

import { useEffect, useState, useCallback } from "react";
import { format, parseISO } from "date-fns";
import { BarChart3, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { TimelineRange } from "./StatisticsShell";

export interface DrivingStatisticsDashboardProps {
  vehicleId: string;
  dateRange: TimelineRange;
  /** Timeline preset to derive period: today/7days -> day, month -> month, year -> year */
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
  avg_energy_per_session_kwh: number;
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
        return format(d, "yyyy MMM");
      case "week":
        return `Week ${format(d, "I")} ${format(d, "yyyy-MM-dd")}`;
      default:
        return format(d, "yyyy-MM-dd");
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
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-iv-muted" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-iv-muted">
        Statistics for the car by period. Not all data can be provided for every car type. Missing information can be
        added in Trips or Charging Sessions.
      </p>
      <div className="overflow-hidden rounded-lg border border-iv-border bg-iv-surface">
        <div className="flex items-center gap-2 border-b border-iv-border px-4 py-3">
          <BarChart3 className="h-5 w-5 text-iv-muted" />
          <h3 className="font-medium">Statistics (per {period})</h3>
        </div>
        {rows.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-iv-muted">No data for the selected period.</div>
        ) : (
          <>
            {/* Mobile card view */}
            <div className="block sm:hidden divide-y divide-iv-border/50">
              {rows.map((r) => (
                <div key={r.period} className="px-4 py-3">
                  <p className="text-xs font-semibold text-iv-cyan mb-2">
                    {formatPeriodLabel(r.period, period)}
                  </p>
                  <div className="grid grid-cols-[6.5rem_1fr] gap-y-1 text-xs">
                    <span className="text-iv-muted">Drives</span>
                    <span className="text-iv-text">{r.drives_count}</span>
                    <span className="text-iv-muted">Time driven</span>
                    <span className="text-iv-text">{formatDuration(r.time_driven_seconds)}</span>
                    <span className="text-iv-muted">Distance</span>
                    <span className="text-iv-text">{r.total_distance_km.toFixed(1)} km</span>
                    <span className="text-iv-muted">Median dist.</span>
                    <span className="text-iv-text">{r.median_distance_km != null ? r.median_distance_km.toFixed(1) : "—"} km</span>
                    <span className="text-iv-muted">Charges</span>
                    <span className="text-iv-text">{r.charging_sessions_count}</span>
                    <span className="text-iv-muted">Time charging</span>
                    <span className="text-iv-text">{formatDuration(r.time_charging_seconds)}</span>
                    <span className="text-iv-muted">Energy</span>
                    <span className="text-iv-text">{r.total_energy_kwh.toFixed(2)} kWh</span>
                  </div>
                </div>
              ))}
            </div>
            {/* Desktop table view */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-iv-border text-left text-iv-muted">
                    <th className="px-4 py-2 font-medium">Period</th>
                    <th className="px-4 py-2 font-medium"># Drives</th>
                    <th className="px-4 py-2 font-medium">Time driven</th>
                    <th className="px-4 py-2 font-medium">Distance (km)</th>
                    <th className="px-4 py-2 font-medium">Median dist. (km)</th>
                    <th className="px-4 py-2 font-medium"># Charges</th>
                    <th className="px-4 py-2 font-medium">Time charging</th>
                    <th className="px-4 py-2 font-medium">Energy (kWh)</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.period} className="border-b border-iv-border/50 last:border-0">
                      <td className="px-4 py-2">{formatPeriodLabel(r.period, period)}</td>
                      <td className="px-4 py-2">{r.drives_count}</td>
                      <td className="px-4 py-2">{formatDuration(r.time_driven_seconds)}</td>
                      <td className="px-4 py-2">{r.total_distance_km.toFixed(1)}</td>
                      <td className="px-4 py-2">{r.median_distance_km != null ? r.median_distance_km.toFixed(1) : "—"}</td>
                      <td className="px-4 py-2">{r.charging_sessions_count}</td>
                      <td className="px-4 py-2">{formatDuration(r.time_charging_seconds)}</td>
                      <td className="px-4 py-2">{r.total_energy_kwh.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
