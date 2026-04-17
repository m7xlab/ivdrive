"use client";

import { useEffect, useState, useCallback } from "react";
import { format, parseISO } from "date-fns";
import { BarChart3, Loader2, Zap, Battery } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { api } from "@/lib/api";
import type { TimelineRange } from "./StatisticsShell";

export interface ChargingStatisticsDashboardProps {
  vehicleId: string;
  dateRange: TimelineRange;
  period?: "day" | "week" | "month" | "year";
}

interface StatisticsRow {
  period: string;
  drives_count: number;
  total_distance_km: number;
  charging_sessions_count: number;
  total_energy_kwh: number;
  avg_energy_per_session_kwh: number;
}

export function ChargingStatisticsDashboard({
  vehicleId,
  dateRange,
  period = "day",
}: ChargingStatisticsDashboardProps) {
  const [stats, setStats] = useState<StatisticsRow[]>([]);
  const [loading, setLoading] = useState(true);

  const fromISO = dateRange.from.toISOString();
  const toISO = dateRange.to.toISOString();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.getStatistics(vehicleId, period, 30, fromISO, toISO);
      setStats(list ?? []);
    } catch {
      setStats([]);
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

  const totalCharges = stats.reduce((acc, r) => acc + r.charging_sessions_count, 0);
  const totalEnergy = stats.reduce((acc, r) => acc + r.total_energy_kwh, 0);

  const chartData = stats
    .slice()
    .reverse()
    .map((r) => {
      let label = r.period;
      try {
        const d = parseISO(r.period.replace("Z", "+00:00"));
        if (period === "year") label = format(d, "yyyy");
        else if (period === "month") label = format(d, "MMM yyyy");
        else if (period === "week") label = `W${format(d, "I")}`;
        else label = format(d, "d MMM");
      } catch {
        // keep raw
      }
      return {
        period: label,
        energy_kwh: r.total_energy_kwh,
        sessions: r.charging_sessions_count,
      };
    });

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
        Aggregate charging data by period. Total number of charging sessions and energy charged.
      </p>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-iv-surface p-4">
          <div className="rounded-lg bg-iv-green/15 p-3">
            <Zap className="h-6 w-6 text-iv-green" />
          </div>
          <div>
            <p className="text-xs font-medium text-iv-muted">Total Charges</p>
            <p className="text-2xl font-bold text-iv-text">{totalCharges}</p>
            <p className="text-xs text-iv-muted">sessions in range</p>
          </div>
        </div>
        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-iv-surface p-4">
          <div className="rounded-lg bg-iv-green/15 p-3">
            <Battery className="h-6 w-6 text-iv-green" />
          </div>
          <div>
            <p className="text-xs font-medium text-iv-muted">Total Energy</p>
            <p className="text-2xl font-bold text-iv-text">{totalEnergy.toFixed(1)} kWh</p>
            <p className="text-xs text-iv-muted">in range</p>
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-iv-border bg-iv-surface">
        <div className="flex items-center gap-2 border-b border-iv-border px-4 py-3">
          <BarChart3 className="h-5 w-5 text-iv-muted" />
          <h3 className="font-medium">Energy charged by period</h3>
        </div>
        {chartData.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-iv-muted">No charging data in the selected period.</div>
        ) : (
          <div className="p-4">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
                <XAxis dataKey="period" tick={{ fontSize: 12 }} className="text-iv-muted" />
                <YAxis tick={{ fontSize: 12 }} className="text-iv-muted" label={{ value: "kWh", angle: -90, position: "insideLeft" }} />
                <Tooltip
                  contentStyle={{ backgroundColor: "var(--iv-bg)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                  labelStyle={{ color: "var(--iv-muted)" }}
                  formatter={(value: number) => [value.toFixed(2), "Energy (kWh)"]}
                />
                <Bar dataKey="energy_kwh" fill="var(--iv-green)" radius={[4, 4, 0, 0]} name="Energy (kWh)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}
