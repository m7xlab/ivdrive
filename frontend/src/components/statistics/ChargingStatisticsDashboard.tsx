"use client";

import { useEffect, useState, useCallback } from "react";
import { format, parseISO } from "date-fns";
import { BarChart3, Loader2, Zap, Battery, Banknote, PieChart } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart as RePieChart, Pie, Cell, Legend } from "recharts";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";
import type { TimelineRange } from "./StatisticsShell";
import { calculateStatisticsLimit } from "@/lib/periodLimit";

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

interface TypeTotals {
  sessions_count: number;
  total_kwh: number;
  total_paid: number;
}

interface Economics {
  total_paid_eur: number;
  subscription_fees_eur: number;
  subscription_savings_eur: number;
  total_cost_with_fees_eur: number;
  by_type: Record<string, TypeTotals>;
}

const TYPE_COLORS: Record<string, string> = {
  subscription: "var(--iv-green)",
  home: "var(--iv-cyan)",
  public: "#f59e0b",
  unknown: "var(--iv-muted)",
};

function localYmd(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function ChargingStatisticsDashboard({
  vehicleId,
  dateRange,
  period = "day",
}: ChargingStatisticsDashboardProps) {
  const { formatMoneyFromEur } = useLocale();
  const [stats, setStats] = useState<StatisticsRow[]>([]);
  const [economics, setEconomics] = useState<Economics | null>(null);
  const [loading, setLoading] = useState(true);

  const fromISO = dateRange.from.toISOString();
  const toISO = dateRange.to.toISOString();
  const fromDate = localYmd(dateRange.from);
  const toDate = localYmd(dateRange.to);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const limit = calculateStatisticsLimit(period, fromISO, toISO);
      const [list, econ] = await Promise.all([
        api.getStatistics(vehicleId, period, limit, fromISO, toISO),
        api.getChargingEconomics(vehicleId, fromDate, toDate).catch(() => null),
      ]);
      setStats(list ?? []);
      setEconomics(econ);
    } catch {
      setStats([]);
      setEconomics(null);
    } finally {
      setLoading(false);
    }
  }, [vehicleId, period, fromISO, toISO, fromDate, toDate]);

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

  const pieData = economics
    ? Object.entries(economics.by_type || {})
        .filter(([, v]) => v && v.total_kwh > 0)
        .map(([key, v]) => ({ name: key, value: v.total_kwh, paid: v.total_paid }))
    : [];

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
        Aggregate charging data by period. Session energy, plus cost breakdown when receipts or charging plans are set.
      </p>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-iv-surface p-4">
          <div className="rounded-lg bg-iv-green/15 p-3">
            <Banknote className="h-6 w-6 text-iv-green" />
          </div>
          <div>
            <p className="text-xs font-medium text-iv-muted">Paid + fees</p>
            <p className="text-2xl font-bold text-iv-text">
              {formatMoneyFromEur(economics?.total_cost_with_fees_eur ?? economics?.total_paid_eur)}
            </p>
            <p className="text-xs text-iv-muted">
              fees {formatMoneyFromEur(economics?.subscription_fees_eur ?? 0)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-iv-surface p-4">
          <div className="rounded-lg bg-iv-green/15 p-3">
            <PieChart className="h-6 w-6 text-iv-green" />
          </div>
          <div>
            <p className="text-xs font-medium text-iv-muted">Subscription savings</p>
            <p className="text-2xl font-bold text-iv-text">
              {formatMoneyFromEur(economics?.subscription_savings_eur ?? 0)}
            </p>
            <p className="text-xs text-iv-muted">vs à-la-carte overage rate</p>
          </div>
        </div>
      </div>

      {pieData.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-iv-border bg-iv-surface">
          <div className="flex items-center gap-2 border-b border-iv-border px-4 py-3">
            <PieChart className="h-5 w-5 text-iv-muted" />
            <h3 className="font-medium">Energy by plan type</h3>
          </div>
          <div className="p-4">
            <ResponsiveContainer width="100%" height={240}>
              <RePieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={50} outerRadius={80} label>
                  {pieData.map((entry) => (
                    <Cell key={entry.name} fill={TYPE_COLORS[entry.name] || TYPE_COLORS.unknown} />
                  ))}
                </Pie>
                <Legend />
                <Tooltip
                  contentStyle={{ backgroundColor: "var(--iv-charcoal)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                  formatter={(value: number, name: string) => [`${value.toFixed(1)} kWh`, name]}
                />
              </RePieChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

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
                  contentStyle={{ backgroundColor: "var(--iv-charcoal)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                  labelStyle={{ color: "var(--iv-muted)" }}
                  itemStyle={{ color: "var(--iv-text)" }}
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
