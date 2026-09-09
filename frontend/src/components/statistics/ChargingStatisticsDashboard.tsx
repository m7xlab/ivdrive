"use client";

import { useEffect, useState, useCallback } from "react";
import { format, parseISO } from "date-fns";
import { BarChart3, Loader2, Zap, Battery, Banknote, PieChart, CreditCard } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart as RePieChart, Pie, Cell } from "recharts";
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
  by_plan?: Array<{
    plan_id: string | null;
    plan_name: string;
    plan_type: string;
    sessions_count: number;
    total_kwh: number;
    total_paid: number;
  }>;
  subscription_usage?: Array<{
    plan_id: string;
    plan_name: string;
    allotment_kwh: number | null;
    used_kwh: number;
    remaining_kwh: number | null;
    used_pct: number | null;
    allocated_eur: number;
    remaining_fee_eur: number | null;
    period_fee_eur: number | null;
    overage_kwh: number;
    saved_vs_public_eur: number | null;
    included_rate_eur: number | null;
    overage_rate_eur: number | null;
    sessions_count: number;
  }>;
}

const PLAN_COLORS = ["var(--iv-green)", "var(--iv-cyan)", "#f59e0b", "#818cf8", "#fb7185", "var(--iv-muted)"];

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

  const pieData = economics?.by_plan?.length
    ? economics.by_plan
        .filter((v) => v && v.total_kwh > 0)
        .map((v) => ({ name: v.plan_name, value: v.total_kwh, paid: v.total_paid }))
    : economics
      ? Object.entries(economics.by_type || {})
          .filter(([, v]) => v && v.total_kwh > 0)
          .map(([key, v]) => ({ name: key, value: v.total_kwh, paid: v.total_paid }))
      : [];
  const pieTotal = pieData.reduce((sum, row) => sum + row.value, 0);
  const usage = economics?.subscription_usage ?? [];

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
        Session energy, named charging-plan usage, and savings versus the public walk-up rate.
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
            <p className="text-xs font-medium text-iv-muted">Plan cost</p>
            <p className="text-2xl font-bold text-iv-text">
              {formatMoneyFromEur(economics?.total_cost_with_fees_eur ?? economics?.total_paid_eur)}
            </p>
            <p className="text-xs text-iv-muted">
              allocated this range
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
            <p className="text-xs text-iv-muted">vs public walk-up rate</p>
          </div>
        </div>
      </div>

      {pieData.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-iv-border bg-iv-surface">
          <div className="flex items-center gap-2 border-b border-iv-border px-4 py-3">
            <PieChart className="h-5 w-5 text-iv-muted" />
            <h3 className="font-medium">Energy by charging plan</h3>
          </div>
          <div className="grid items-center gap-6 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(16rem,20rem)]">
            <div className="relative mx-auto w-full max-w-[320px]">
              <ResponsiveContainer width="100%" height={260}>
                <RePieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={72}
                    outerRadius={104}
                    paddingAngle={2}
                    stroke="var(--iv-surface)"
                    strokeWidth={2}
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={entry.name} fill={PLAN_COLORS[index % PLAN_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: "var(--iv-charcoal)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                    formatter={(value: number, name: string) => [`${value.toFixed(1)} kWh`, name]}
                  />
                </RePieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                <p className="text-2xl font-semibold tabular-nums text-iv-text">{pieTotal.toFixed(1)}</p>
                <p className="text-xs uppercase tracking-wide text-iv-muted">kWh total</p>
              </div>
            </div>
            <ul className="space-y-3">
              {pieData.map((entry, index) => {
                const share = pieTotal > 0 ? (entry.value / pieTotal) * 100 : 0;
                return (
                  <li key={entry.name} className="flex items-start justify-between gap-3">
                    <span className="flex min-w-0 items-center gap-2">
                      <span
                        className="mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: PLAN_COLORS[index % PLAN_COLORS.length] }}
                        aria-hidden
                      />
                      <span className="truncate text-sm text-iv-text">{entry.name}</span>
                    </span>
                    <span className="shrink-0 text-right">
                      <span className="block text-sm font-semibold tabular-nums text-iv-text">
                        {entry.value.toFixed(1)} kWh
                      </span>
                      <span className="text-xs tabular-nums text-iv-muted">{share.toFixed(0)}%</span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}

      {usage.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-iv-border bg-iv-surface">
          <div className="flex items-center gap-2 border-b border-iv-border px-4 py-3">
            <CreditCard className="h-5 w-5 text-iv-muted" />
            <h3 className="font-medium">Subscription usage (current billing period)</h3>
          </div>
          <div className="space-y-4 p-4">
            {usage.map((plan) => {
              const pct = plan.used_pct ?? 0;
              return (
                <div key={plan.plan_id}>
                  <div className="mb-1 flex items-baseline justify-between gap-3">
                    <p className="font-medium text-iv-text">{plan.plan_name}</p>
                    <p className="text-xs text-iv-muted">
                      {plan.sessions_count} session{plan.sessions_count === 1 ? "" : "s"} this period
                    </p>
                  </div>
                  {plan.allotment_kwh != null ? (
                    <>
                      <div className="h-2 overflow-hidden rounded-full bg-iv-border">
                        <div
                          className="h-full rounded-full bg-iv-green"
                          style={{ width: `${Math.min(100, pct)}%` }}
                        />
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                        <p className="text-iv-muted">
                          Used <span className="font-medium text-iv-text">{plan.used_kwh.toFixed(2)} kWh</span>
                        </p>
                        <p className="text-iv-muted">
                          Left <span className="font-medium text-iv-text">{plan.remaining_kwh?.toFixed(2) ?? "—"} kWh</span>
                        </p>
                        <p className="text-iv-muted">
                          On plan <span className="font-medium text-iv-text">{formatMoneyFromEur(plan.allocated_eur)}</span>
                        </p>
                        <p className="text-iv-muted">
                          Fee left <span className="font-medium text-iv-text">{formatMoneyFromEur(plan.remaining_fee_eur)}</span>
                        </p>
                      </div>
                      {plan.overage_kwh > 0 && (
                        <p className="mt-1 text-xs text-amber-400">
                          {plan.overage_kwh.toFixed(2)} kWh over included at the public walk-up rate
                        </p>
                      )}
                      {plan.saved_vs_public_eur != null && plan.overage_rate_eur != null && (
                        <p className="mt-1 text-xs text-iv-cyan">
                          Saved {formatMoneyFromEur(plan.saved_vs_public_eur)} vs public walk-up
                          {plan.included_rate_eur != null
                            ? ` (${formatMoneyFromEur(plan.included_rate_eur, 3)}/kWh included)`
                            : ""}
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="text-sm text-iv-muted">
                      {plan.used_kwh.toFixed(2)} kWh · {formatMoneyFromEur(plan.allocated_eur)} on plan
                    </p>
                  )}
                </div>
              );
            })}
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
