"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Loader2, Battery, TrendingDown, Calendar, Activity } from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

interface SoHDataPoint {
  date: string;
  session_start_soc: number;
  session_end_soc: number;
  soc_delta_pct: number;
  energy_kwh: number;
  estimated_capacity_kwh: number;
}

interface SoHMonthlyTrend {
  month: string;
  estimated_capacity_kwh: number;
  sample_count: number;
}

interface SoHSummary {
  nominal_capacity_kwh: number;
  current_estimate_kwh: number | null;
  degradation_pct: number | null;
  sessions_analyzed: number;
  valid_estimates: number;
}

interface SoHResponse {
  data_points: SoHDataPoint[];
  monthly_trend: SoHMonthlyTrend[];
  summary: SoHSummary;
  formula: string;
  message: string;
}

export function SoHDashboard({ vehicleId, dateRange }: { vehicleId: string; dateRange?: { from: Date; to: Date } }) {
  const [data, setData] = useState<SoHResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSoH = async () => {
      try {
        setLoading(true);
        const opts = dateRange
          ? { fromDate: dateRange.from.toISOString(), toDate: dateRange.to.toISOString() }
          : undefined;
        const res = await api.getSoHTrend(vehicleId, opts);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch SoH trend data", err);
      } finally {
        setLoading(false);
      }
    };
    fetchSoH();
  }, [vehicleId, dateRange?.from?.toISOString(), dateRange?.to?.toISOString()]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 glass rounded-2xl border border-iv-border p-6 mt-6">
        <Loader2 className="h-8 w-8 animate-spin text-iv-muted" />
      </div>
    );
  }

  if (!data || data.data_points.length === 0) {
    return (
      <div className="glass rounded-2xl border border-iv-border p-6 mt-6">
        <div className="flex items-center gap-2 mb-2">
          <Battery className="h-5 w-5 text-iv-muted" />
          <h3 className="text-lg font-bold text-iv-text">Battery Health (SoH) Tracking</h3>
        </div>
        <p className="text-sm text-iv-text-muted">
          Not enough charging session data to calculate battery health degradation.
        </p>
      </div>
    );
  }

  const { summary, monthly_trend, data_points } = data;

  // Calculate health status
  const getHealthStatus = (degradation: number | null) => {
    if (degradation === null) return { label: "Unknown", color: "text-iv-muted" };
    if (degradation < 5) return { label: "Excellent", color: "text-iv-green" };
    if (degradation < 10) return { label: "Good", color: "text-iv-cyan" };
    if (degradation < 20) return { label: "Fair", color: "text-iv-yellow" };
    return { label: "Replace Soon", color: "text-iv-red" };
  };

  const healthStatus = getHealthStatus(summary.degradation_pct);

  // Prepare chart data - reverse for chronological order
  const chartData = [...monthly_trend].reverse();

  return (
    <div className="space-y-6 mt-6">
      {/* Formula explanation */}
      <div className="glass rounded-2xl border border-iv-border p-6">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="h-5 w-5 text-iv-cyan" />
          <h3 className="text-lg font-bold text-iv-text">Battery Health (SoH) Tracking</h3>
        </div>

        <div className="bg-iv-surface/50 rounded-xl p-4 border border-iv-border mb-4">
          <p className="text-xs text-iv-text-muted uppercase tracking-wider mb-2">Formula Used</p>
          <div className="font-mono text-sm p-2 bg-iv-bg rounded border border-iv-border/50">
            <span className="text-iv-text">true_capacity_kwh = energy_kwh_delivered / soc_delta × 100</span>
          </div>
          <p className="text-xs text-iv-muted mt-2">
            Analyzes charging sessions with ≥10% SoC change to extrapolate true 100% battery capacity.
            Tracking this over time reveals the Battery Degradation Curve.
          </p>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="flex items-center gap-3 rounded-lg border border-iv-border bg-iv-surface p-4">
            <div className="rounded-lg bg-iv-cyan/15 p-3">
              <Battery className="h-6 w-6 text-iv-cyan" />
            </div>
            <div>
              <p className="text-xs font-medium text-iv-muted">Nominal Capacity</p>
              <p className="text-xl font-bold text-iv-text">{summary.nominal_capacity_kwh} kWh</p>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-lg border border-iv-border bg-iv-surface p-4">
            <div className="rounded-lg bg-iv-green/15 p-3">
              <Activity className="h-6 w-6 text-iv-green" />
            </div>
            <div>
              <p className="text-xs font-medium text-iv-muted">Current Estimate</p>
              <p className="text-xl font-bold text-iv-text">
                {summary.current_estimate_kwh ? `${summary.current_estimate_kwh} kWh` : "N/A"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-lg border border-iv-border bg-iv-surface p-4">
            <div className="rounded-lg bg-red-500/15 p-3">
              <TrendingDown className="h-6 w-6 text-red-500" />
            </div>
            <div>
              <p className="text-xs font-medium text-iv-muted">Degradation</p>
              <p className="text-xl font-bold text-red-400">
                {summary.degradation_pct ? `${summary.degradation_pct}%` : "N/A"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-lg border border-iv-border bg-iv-surface p-4">
            <div className={`rounded-lg p-3 ${healthStatus.color.replace("text-", "bg-")}/15`}>
              <Calendar className={`h-6 w-6 ${healthStatus.color}`} />
            </div>
            <div>
              <p className="text-xs font-medium text-iv-muted">Health Status</p>
              <p className={`text-xl font-bold ${healthStatus.color}`}>{healthStatus.label}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Degradation chart */}
      <div className="glass rounded-2xl border border-iv-border p-6">
        <h3 className="text-lg font-bold text-iv-text mb-4">Battery Degradation Curve</h3>

        {chartData.length === 0 ? (
          <div className="text-center py-8 text-iv-muted">No monthly data available</div>
        ) : (
          <div className="h-80 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
                <XAxis
                  dataKey="month"
                  className="text-iv-muted text-xs"
                  label={{ value: "Month", position: "insideBottom", offset: -5 }}
                />
                <YAxis
                  className="text-iv-muted text-xs"
                  domain={[
                    (dataMin: number) => Math.floor(dataMin / 5) * 5 - 5,
                    (dataMax: number) => Math.ceil(dataMax / 5) * 5 + 5,
                  ]}
                  label={{ value: "Capacity (kWh)", angle: -90, position: "insideLeft" }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--iv-bg)",
                    border: "1px solid var(--iv-border)",
                    borderRadius: "8px",
                  }}
                  itemStyle={{ color: "var(--iv-text)" }}
                  formatter={(value: number) => [`${value.toFixed(2)} kWh`, "Est. Capacity"]}
                  labelFormatter={(label) => `Month: ${label}`}
                />
                <Legend wrapperStyle={{ paddingTop: "16px" }} />
                {/* Nominal capacity reference line */}
                <ReferenceLine
                  y={summary.nominal_capacity_kwh}
                  stroke="var(--iv-green)"
                  strokeDasharray="5 5"
                  strokeWidth={2}
                  label={{
                    value: `Nominal: ${summary.nominal_capacity_kwh} kWh`,
                    position: "right",
                    fill: "var(--iv-green)",
                    fontSize: 11,
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="estimated_capacity_kwh"
                  stroke="var(--iv-cyan)"
                  strokeWidth={2}
                  dot={{ fill: "var(--iv-cyan)", strokeWidth: 2 }}
                  activeDot={{ r: 6, fill: "var(--iv-cyan)" }}
                  name="Estimated Capacity"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Degradation message */}
      {data.message && (
        <div className="bg-iv-surface/50 border border-iv-border rounded-xl p-4">
          <p className="text-sm text-iv-text">
            <span className="font-medium text-iv-cyan">Analysis:</span> {data.message}
          </p>
        </div>
      )}
    </div>
  );
}
