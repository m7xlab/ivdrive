"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { format, parseISO } from "date-fns";
import { Loader2, Zap, Battery, Euro, Plug, TrendingUp, Calendar } from "lucide-react";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { api } from "@/lib/api";
import type { TimelineRange } from "./StatisticsShell";

export interface ChargingEconomicsDashboardProps {
  vehicleId: string;
  dateRange?: TimelineRange;
}

// ── Types ────────────────────────────────────────────────────────────────────

interface StatisticsRow {
  period: string;
  charging_sessions_count: number;
  total_energy_kwh: number;
  avg_energy_per_session_kwh: number;
}

interface ChargingSessionRow {
  id: number;
  session_start: string | null;
  session_end: string | null;
  start_level: number | null;
  end_level: number | null;
  energy_kwh: number | null;
  base_cost_eur: number | null;
  actual_cost_eur: number | null;
  provider_name: string | null;
  charging_type: string | null;
  avg_temp_celsius: number | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatEUR(v: number | null | undefined): string {
  if (v == null) return "—";
  return `€${v.toFixed(2)}`;
}

function formatKwh(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v.toFixed(1)} kWh`;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ChargingEconomicsDashboard({ vehicleId, dateRange }: ChargingEconomicsDashboardProps) {
  const [stats, setStats] = useState<StatisticsRow[]>([]);
  const [sessions, setSessions] = useState<ChargingSessionRow[]>([]);
  const [loading, setLoading] = useState(true);

  const fromISO = dateRange?.from?.toISOString();
  const toISO = dateRange?.to?.toISOString();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsData, sessionsData] = await Promise.allSettled([
        api.getStatistics(vehicleId, "day", 30, fromISO, toISO),
        api.getChargingSessions(vehicleId, 500, fromISO, toISO),
      ]);

      setStats(statsData.status === "fulfilled" ? (statsData.value ?? []) : []);
      setSessions(sessionsData.status === "fulfilled" ? (sessionsData.value ?? []) : []);
    } catch {
      // swallow
    } finally {
      setLoading(false);
    }
  }, [vehicleId, fromISO, toISO]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ── KPI derivations ─────────────────────────────────────────────────────────
  const totalSessions = sessions.length;
  const totalEnergy = sessions.reduce((acc, s) => acc + (s.energy_kwh ?? 0), 0);
  const totalCost = sessions.reduce((acc, s) => acc + (s.actual_cost_eur ?? s.base_cost_eur ?? 0), 0);
  const avgCostPerKwh = totalEnergy > 0 ? totalCost / totalEnergy : 0;

  // AC vs DC breakdown
  const acSessions = sessions.filter((s) => s.charging_type === "AC");
  const dcSessions = sessions.filter((s) => s.charging_type === "DC");
  const acEnergy = acSessions.reduce((acc, s) => acc + (s.energy_kwh ?? 0), 0);
  const dcEnergy = dcSessions.reduce((acc, s) => acc + (s.energy_kwh ?? 0), 0);

  // Chart data: energy by period (from stats) + cost trend (from sessions by day)
  const chartData = useMemo(() => {
    const periodMap = new Map<string, { period: string; energy_kwh: number; sessions: number; cost: number }>();

    // Seed from stats (energy + session count by day)
    for (const row of stats) {
      let label = row.period;
      try {
        const d = parseISO(row.period.replace("Z", "+00:00"));
        label = format(d, "d MMM");
      } catch { /* keep raw */ }
      const existing = periodMap.get(label) ?? { period: label, energy_kwh: 0, sessions: 0, cost: 0 };
      existing.energy_kwh += row.total_energy_kwh;
      existing.sessions += row.charging_sessions_count;
      periodMap.set(label, existing);
    }

    // Add cost data from sessions
    for (const s of sessions) {
      if (!s.session_start) continue;
      const day = format(parseISO(s.session_start), "d MMM");
      const cost = s.actual_cost_eur ?? s.base_cost_eur ?? 0;
      const existing = periodMap.get(day) ?? { period: day, energy_kwh: 0, sessions: 0, cost: 0 };
      existing.cost += cost;
      periodMap.set(day, existing);
    }

    return [...periodMap.values()].slice(-14); // last 14 periods
  }, [stats, sessions]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-iv-muted" />
      </div>
    );
  }

  const hasData = sessions.length > 0 || stats.length > 0;

  if (!hasData) {
    return (
      <div className="py-24 text-center text-sm text-iv-muted">
        No charging data for the selected period.
      </div>
    );
  }

  return (
    <div className="space-y-6">

      {/* ── KPI Row ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="glass rounded-xl p-4 space-y-1">
          <div className="flex items-center gap-2">
            <Plug size={14} className="text-iv-cyan" />
            <span className="text-[10px] font-semibold text-iv-muted uppercase tracking-wide">Sessions</span>
          </div>
          <p className="text-2xl font-bold text-iv-text">{totalSessions}</p>
          <p className="text-xs text-iv-muted">{stats.reduce((a, r) => a + r.charging_sessions_count, 0)} in period</p>
        </div>

        <div className="glass rounded-xl p-4 space-y-1">
          <div className="flex items-center gap-2">
            <Battery size={14} className="text-iv-green" />
            <span className="text-[10px] font-semibold text-iv-muted uppercase tracking-wide">Energy</span>
          </div>
          <p className="text-2xl font-bold text-iv-text">{totalEnergy.toFixed(1)} <span className="text-sm font-normal text-iv-muted">kWh</span></p>
          <p className="text-xs text-iv-muted">{avgCostPerKwh.toFixed(3)} €/kWh avg</p>
        </div>

        <div className="glass rounded-xl p-4 space-y-1">
          <div className="flex items-center gap-2">
            <Euro size={14} className="text-iv-yellow" />
            <span className="text-[10px] font-semibold text-iv-muted uppercase tracking-wide">Total Cost</span>
          </div>
          <p className="text-2xl font-bold text-iv-text">{formatEUR(totalCost)}</p>
          <p className="text-xs text-iv-muted">actual cost</p>
        </div>

        <div className="glass rounded-xl p-4 space-y-1">
          <div className="flex items-center gap-2">
            <TrendingUp size={14} className="text-iv-purple" />
            <span className="text-[10px] font-semibold text-iv-muted uppercase tracking-wide">AC / DC Split</span>
          </div>
          <p className="text-2xl font-bold text-iv-text">{acSessions.length} / {dcSessions.length}</p>
          <p className="text-xs text-iv-muted">AC/DC sessions</p>
        </div>
      </div>

      {/* ── Energy + Cost Trend Chart ── */}
      {chartData.length > 1 && (
        <div className="glass rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-iv-text">Charging Energy & Cost Trend</h3>
            <span className="text-xs bg-iv-surface border border-iv-border text-iv-muted px-2 py-0.5 rounded-full">Last 14 days</span>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
              <XAxis dataKey="period" tick={{ fontSize: 11 }} className="text-iv-muted" tickLine={false} />
              <YAxis yAxisId="energy" orientation="left" tick={{ fontSize: 11 }} className="text-iv-muted" tickLine={false} axisLine={false} label={{ value: "kWh", angle: -90, position: "insideLeft" }} />
              <YAxis yAxisId="cost" orientation="right" tick={{ fontSize: 11 }} className="text-iv-muted" tickLine={false} axisLine={false} label={{ value: "€", angle: 90, position: "insideRight" }} />
              <Tooltip
                contentStyle={{ backgroundColor: "var(--iv-bg)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                labelStyle={{ color: "var(--iv-muted)" }}
                formatter={(value: number, name: string) => [
                  name === "energy_kwh" ? `${value.toFixed(1)} kWh` : `€${value.toFixed(2)}`,
                  name === "energy_kwh" ? "Energy" : "Cost"
                ]}
              />
              <Legend />
              <Line yAxisId="energy" type="monotone" dataKey="energy_kwh" name="Energy (kWh)" stroke="var(--iv-green)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
              <Line yAxisId="cost" type="monotone" dataKey="cost" name="Cost (€)" stroke="var(--iv-yellow)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── AC vs DC Breakdown ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {[
          { label: "AC Charging", sessions: acSessions.length, energy: acEnergy, type: "AC" },
          { label: "DC Charging", sessions: dcSessions.length, energy: dcEnergy, type: "DC" },
        ].map(({ label, sessions: cnt, energy, type }) => (
          <div key={type} className="glass rounded-xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-iv-text">{label}</h3>
              <span className={`text-xs px-2 py-0.5 rounded-full ${type === "AC" ? "bg-iv-cyan/10 text-iv-cyan" : "bg-iv-green/10 text-iv-green"}`}>
                {type}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${type === "AC" ? "bg-iv-cyan/10" : "bg-iv-green/10"}`}>
                  <Plug size={16} className={type === "AC" ? "text-iv-cyan" : "text-iv-green"} />
                </div>
                <div>
                  <p className="text-xs text-iv-muted">Sessions</p>
                  <p className="text-xl font-bold text-iv-text">{cnt}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${type === "AC" ? "bg-iv-cyan/10" : "bg-iv-green/10"}`}>
                  <Battery size={16} className={type === "AC" ? "text-iv-cyan" : "text-iv-green"} />
                </div>
                <div>
                  <p className="text-xs text-iv-muted">Energy</p>
                  <p className="text-xl font-bold text-iv-text">{energy.toFixed(1)} <span className="text-sm font-normal text-iv-muted">kWh</span></p>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* ── Recent Sessions Table ── */}
      {sessions.length > 0 && (
        <div className="glass rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-iv-text flex items-center gap-2">
            <Calendar size={14} /> Recent Charging Sessions
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-iv-border/50">
                  <th className="text-left text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Date</th>
                  <th className="text-left text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Type</th>
                  <th className="text-right text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Energy</th>
                  <th className="text-right text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Start → End</th>
                  <th className="text-right text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Cost</th>
                  <th className="text-left text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Provider</th>
                </tr>
              </thead>
              <tbody className="space-y-1">
                {sessions.slice(0, 15).map((s) => {
                  const cost = s.actual_cost_eur ?? s.base_cost_eur;
                  const levelDelta = s.end_level != null && s.start_level != null
                    ? `+${(s.end_level - s.start_level).toFixed(0)}%`
                    : s.end_level != null ? `${s.end_level.toFixed(0)}%` : "—";
                  return (
                    <tr key={s.id} className="border-b border-iv-border/20 hover:bg-iv-surface/40 transition-colors">
                      <td className="py-2 text-iv-text">
                        {s.session_start ? format(parseISO(s.session_start), "d MMM HH:mm") : "—"}
                      </td>
                      <td className="py-2">
                        <span className={`text-xs px-1.5 py-0.5 rounded-full ${s.charging_type === "DC" ? "bg-iv-green/10 text-iv-green" : "bg-iv-cyan/10 text-iv-cyan"}`}>
                          {s.charging_type ?? "?"}
                        </span>
                      </td>
                      <td className="py-2 text-right text-iv-text">{formatKwh(s.energy_kwh)}</td>
                      <td className="py-2 text-right text-iv-muted">
                        {s.start_level != null ? `${s.start_level.toFixed(0)}%` : "—"} → {s.end_level != null ? `${s.end_level.toFixed(0)}%` : "—"}
                        <span className="text-xs text-iv-green ml-1">{levelDelta}</span>
                      </td>
                      <td className="py-2 text-right font-medium text-iv-text">{formatEUR(cost)}</td>
                      <td className="py-2 text-iv-muted truncate max-w-[120px]">{s.provider_name ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Recent Sessions Table ── */}
      {sessions.length > 0 && (
        <div className="glass rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-iv-text flex items-center gap-2">
            <Calendar size={14} /> Recent Charging Sessions
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-iv-border/50">
                  <th className="text-left text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Date</th>
                  <th className="text-left text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Type</th>
                  <th className="text-right text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Energy</th>
                  <th className="text-right text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Start → End</th>
                  <th className="text-right text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Cost</th>
                  <th className="text-left text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Provider</th>
                </tr>
              </thead>
              <tbody className="space-y-1">
                {sessions.slice(0, 15).map((s) => {
                  const cost = s.actual_cost_eur ?? s.base_cost_eur;
                  const levelDelta = s.end_level != null && s.start_level != null
                    ? `+${(s.end_level - s.start_level).toFixed(0)}%`
                    : s.end_level != null ? `${s.end_level.toFixed(0)}%` : "—";
                  return (
                    <tr key={s.id} className="border-b border-iv-border/20 hover:bg-iv-surface/40 transition-colors">
                      <td className="py-2 text-iv-text">
                        {s.session_start ? format(parseISO(s.session_start), "d MMM HH:mm") : "—"}
                      </td>
                      <td className="py-2">
                        <span className={`text-xs px-1.5 py-0.5 rounded-full ${s.charging_type === "DC" ? "bg-iv-green/10 text-iv-green" : "bg-iv-cyan/10 text-iv-cyan"}`}>
                          {s.charging_type ?? "?"}
                        </span>
                      </td>
                      <td className="py-2 text-right text-iv-text">{formatKwh(s.energy_kwh)}</td>
                      <td className="py-2 text-right text-iv-muted">
                        {s.start_level != null ? `${s.start_level.toFixed(0)}%` : "—"} → {s.end_level != null ? `${s.end_level.toFixed(0)}%` : "—"}
                        <span className="text-xs text-iv-green ml-1">{levelDelta}</span>
                      </td>
                      <td className="py-2 text-right font-medium text-iv-text">{formatEUR(cost)}</td>
                      <td className="py-2 text-iv-muted truncate max-w-[120px]">{s.provider_name ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Base Grid Cost vs Public Charger Convenience Fee ── */}
      <ChargingMarkupSection vehicleId={vehicleId} dateRange={dateRange} />

    </div>
  );
}

// ── Sub-component: Base Grid Cost vs DC Provider Markup ─────────────────────

interface ChargingMarkupData {
  sessions: {
    session_id: number;
    session_start: string | null;
    charging_type: string | null;
    energy_kwh: number | null;
    base_grid_cost_eur: number | null;
    paid_eur: number | null;
    markup_eur: number | null;
    provider_name: string | null;
  }[];
  total_energy_kwh: number;
  total_base_grid_cost_eur: number;
  total_paid_eur: number;
  total_markup_eur: number;
  electricity_price_eur_kwh: number;
  country_code: string;
}

function ChargingMarkupSection({
  vehicleId,
  dateRange,
}: {
  vehicleId: string;
  dateRange?: TimelineRange;
}) {
  const [data, setData] = useState<ChargingMarkupData | null>(null);
  const [loading, setLoading] = useState(true);

  const fromISO = dateRange?.from?.toISOString();
  const toISO = dateRange?.to?.toISOString();

  useEffect(() => {
    const fetch_ = async () => {
      try {
        setLoading(true);
        const res = await api.getChargingEconomics(vehicleId, fromISO, toISO);
        setData(res ?? null);
      } catch {
        setData(null);
      } finally {
        setLoading(false);
      }
    };
    fetch_();
  }, [vehicleId, fromISO, toISO]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-iv-muted" />
      </div>
    );
  }

  if (!data || data.sessions.length === 0) {
    return null;
  }

  // Build chart data: top sessions by energy for readability
  const chartData = data.sessions.slice(0, 12).map((s) => ({
    name: s.session_start ? format(parseISO(s.session_start), "d MMM") : `#${s.session_id}`,
    "Grid Base (€)": s.base_grid_cost_eur ?? 0,
    "DC Markup (€)": Math.max(0, s.markup_eur ?? 0),
  }));

  // Add totals row
  chartData.push({
    name: "Total",
    "Grid Base (€)": data.total_base_grid_cost_eur,
    "DC Markup (€)": Math.max(0, data.total_markup_eur),
  });

  return (
    <div className="glass rounded-xl p-5 space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-iv-text">Charging Economics</h3>
        <p className="text-xs text-iv-muted mt-0.5">
          Base Grid Cost vs Public Charger Convenience Fee
          {data.country_code && <span className="ml-1">({data.country_code} grid: €{data.electricity_price_eur_kwh}/kWh)</span>}
        </p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-iv-surface rounded-xl p-4 border border-iv-border/50">
          <p className="text-xs text-iv-muted">Total Energy</p>
          <p className="text-2xl font-bold text-iv-text">{data.total_energy_kwh.toFixed(1)} <span className="text-sm font-normal text-iv-muted">kWh</span></p>
          <p className="text-xs text-iv-muted">{data.sessions.length} sessions</p>
        </div>
        <div className="bg-iv-surface rounded-xl p-4 border border-iv-border/50">
          <p className="text-xs text-iv-muted">Grid Base Cost</p>
          <p className="text-2xl font-bold text-iv-green">€{data.total_base_grid_cost_eur.toFixed(2)}</p>
          <p className="text-xs text-iv-muted">at €{data.electricity_price_eur_kwh}/kWh</p>
        </div>
        <div className="bg-iv-surface rounded-xl p-4 border border-iv-border/50">
          <p className="text-xs text-iv-muted">Total Paid</p>
          <p className="text-2xl font-bold text-iv-text">€{data.total_paid_eur.toFixed(2)}</p>
          <p className="text-xs text-iv-muted">actual cost</p>
        </div>
        <div className="bg-iv-surface rounded-xl p-4 border border-iv-border/50">
          <p className="text-xs text-iv-muted">DC Markup Paid</p>
          <p className="text-2xl font-bold text-rose-400">€{data.total_markup_eur.toFixed(2)}</p>
          <p className="text-xs text-iv-muted">provider convenience fee</p>
        </div>
      </div>

      {/* Stacked bar chart */}
      {chartData.length > 1 && (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} className="stroke-iv-border" />
              <XAxis type="number" tickFormatter={(v) => `€${v}`} tick={{ fontSize: 11 }} className="text-iv-muted" tickLine={false} />
              <YAxis dataKey="name" type="category" tick={{ fontSize: 11 }} className="text-iv-muted" tickLine={false} width={52} />
              <Tooltip
                formatter={(value: number, name: string) => [`€${value.toFixed(2)}`, name]}
                contentStyle={{ backgroundColor: "var(--iv-bg)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                labelStyle={{ color: "var(--iv-muted)" }}
              />
              <Legend wrapperStyle={{ paddingTop: "12px" }} />
              <Bar dataKey="Grid Base (€)" stackId="a" fill="var(--iv-green)" radius={[3, 0, 0, 3]} />
              <Bar dataKey="DC Markup (€)" stackId="a" fill="#F43F5E" radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Per-session breakdown table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-iv-border/50">
              <th className="text-left text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Date</th>
              <th className="text-left text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Type</th>
              <th className="text-right text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">kWh</th>
              <th className="text-right text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Grid Base</th>
              <th className="text-right text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Markup</th>
              <th className="text-right text-xs text-iv-muted font-semibold uppercase tracking-wide pb-2">Paid</th>
            </tr>
          </thead>
          <tbody>
            {data.sessions.slice(0, 15).map((s) => (
              <tr key={s.session_id} className="border-b border-iv-border/20 hover:bg-iv-surface/40 transition-colors">
                <td className="py-2 text-iv-text">
                  {s.session_start ? format(parseISO(s.session_start), "d MMM HH:mm") : "—"}
                </td>
                <td className="py-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded-full ${s.charging_type === "DC" ? "bg-iv-green/10 text-iv-green" : "bg-iv-cyan/10 text-iv-cyan"}`}>
                    {s.charging_type ?? "?"}
                  </span>
                </td>
                <td className="py-2 text-right text-iv-text">{s.energy_kwh?.toFixed(1) ?? "—"}</td>
                <td className="py-2 text-right text-iv-green">€{(s.base_grid_cost_eur ?? 0).toFixed(2)}</td>
                <td className="py-2 text-right text-rose-400">€{(s.markup_eur ?? 0) > 0 ? `+${(s.markup_eur ?? 0).toFixed(2)}` : "€0.00"}</td>
                <td className="py-2 text-right font-medium text-iv-text">€{(s.paid_eur ?? 0).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}