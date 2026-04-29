"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Loader2, Zap, Clock, BatteryWarning } from "lucide-react";
import {
import { formatSmartDuration } from "@/lib/format";
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts";

interface CurvePoint {
  soc_pct: number;
  avg_power_kw: number;
  max_power_kw: number;
  samples: number;
}

interface BracketData {
  label: string;
  energy_kwh: number;
  minutes: number;
  samples: number;
}

interface ChargingAnalysisData {
  curve: CurvePoint[];
  brackets: BracketData[];
  wasted_minutes_80_100: number;
  total_energy_kwh: number;
  total_minutes: number;
  wasted_pct: number;
  message?: string;
}

export function ChargingAnalysisDashboard({
  vehicleId,
  dateRange,
}: {
  vehicleId: string;
  dateRange?: { from: Date; to: Date };
}) {
  const [data, setData] = useState<ChargingAnalysisData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const opts = dateRange
          ? {
              fromDate: dateRange.from.toISOString(),
              toDate: dateRange.to.toISOString(),
            }
          : undefined;
        const res = await api.getChargingCurveIntegralsV2(vehicleId, opts);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch charging analysis", err);
        setData(null);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [
    vehicleId,
    dateRange?.from?.toISOString(),
    dateRange?.to?.toISOString(),
  ]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-iv-muted" />
      </div>
    );
  }

  if (!data || data.curve.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-iv-muted">
        {data?.message || "No charging data available for this period."}
      </div>
    );
  }

  // --- KPI cards ---
  const peakPower =
    data.curve?.length ? Math.max(...data.curve.map((d) => d.avg_power_kw)) : 0;
  const avgPower =
    data.curve?.length
      ? data.curve.reduce((s, d) => s + d.avg_power_kw, 0) / data.curve.length
      : 0;

  // --- Chart data ---
  const chartData = data.brackets.map((b) => ({
    name: b.label,
    "Energy (kWh)": b.energy_kwh,
    "Time (min)": b.minutes,
  }));

  return (
    <div className="space-y-6">
      <p className="text-sm text-iv-muted">
        Fast charging analysis — power curve across SoC and time spent in each
        battery bracket.
      </p>

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-iv-surface p-4">
          <div className="rounded-lg bg-iv-green/15 p-3">
            <Zap className="h-6 w-6 text-iv-green" />
          </div>
          <div>
            <p className="text-xs font-medium text-iv-muted">Peak Power</p>
            <p className="text-2xl font-bold text-iv-text">{peakPower.toFixed(1)} kW</p>
            <p className="text-xs text-iv-muted">max observed</p>
          </div>
        </div>

        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-iv-surface p-4">
          <div className="rounded-lg bg-iv-cyan/15 p-3">
            <Zap className="h-6 w-6 text-iv-cyan" />
          </div>
          <div>
            <p className="text-xs font-medium text-iv-muted">Avg Fast Charging</p>
            <p className="text-2xl font-bold text-iv-text">{avgPower.toFixed(1)} kW</p>
            <p className="text-xs text-iv-muted">across whole curve</p>
          </div>
        </div>

        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-iv-surface p-4">
          <div className="rounded-lg bg-iv-cyan/15 p-3">
            <Clock className="h-6 w-6 text-iv-cyan" />
          </div>
          <div>
            <p className="text-xs font-medium text-iv-muted">Total Time</p>
            <p className="text-2xl font-bold text-iv-text">{formatSmartDuration(data.total_minutes)}</p>
            <p className="text-xs text-iv-muted">in {data.brackets.length} brackets</p>
          </div>
        </div>

        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-iv-surface p-4">
          <div className="rounded-lg bg-red-500/15 p-3">
            <Clock className="h-6 w-6 text-red-500" />
          </div>
          <div>
            <p className="text-xs font-medium text-iv-muted">Time Wasted (80-100%)</p>
            <p className="text-2xl font-bold text-red-400">
              {formatSmartDuration(data.wasted_minutes_80_100)}
            </p>
            <p className="text-xs text-iv-muted">{data.wasted_pct}% of total</p>
          </div>
        </div>
      </div>

      {/* Wasted time warning */}
      {data.wasted_minutes_80_100 > 0 && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
          <p className="text-sm text-iv-text">
            <span className="font-bold text-iv-red">
              Charging 80-100% wastes {formatSmartDuration(data.wasted_minutes_80_100)}utes
            </span>{" "}
            per session (≈{data.wasted_pct}% of total charging time). Consider
            stopping at 80% for daily drives.
          </p>
        </div>
      )}

      {/* Power curve — full width */}
      <div className="overflow-hidden rounded-lg border border-iv-border bg-iv-surface">
        <div className="flex items-center gap-2 border-b border-iv-border px-4 py-3">
          <BatteryWarning className="h-5 w-5 text-iv-muted" />
          <h3 className="font-medium text-iv-text">Charging Power Curve</h3>
        </div>
        <div className="p-4">
          <ResponsiveContainer width="100%" height={280}>
            <LineChart
              data={data.curve}
              margin={{ top: 8, right: 8, left: 8, bottom: 8 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                className="stroke-iv-border"
              />
              <XAxis
                dataKey="soc_pct"
                tick={{ fontSize: 12 }}
                className="text-iv-muted"
                label={{
                  value: "State of Charge (%)",
                  position: "insideBottom",
                  offset: -5,
                }}
              />
              <YAxis
                tick={{ fontSize: 12 }}
                className="text-iv-muted"
                label={{ value: "Power (kW)", angle: -90, position: "insideLeft" }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--iv-bg)",
                  border: "1px solid var(--iv-border)",
                  borderRadius: "8px",
                }}
                labelStyle={{ color: "var(--iv-muted)" }}
                formatter={(
                  value: number,
                  name: string
                ) => [
                  value.toFixed(2),
                  name === "avg_power_kw" ? "Avg Power (kW)" : "Max Power (kW)",
                ]}
                labelFormatter={(label) => `SoC: ${label}%`}
              />
              <Line
                type="monotone"
                dataKey="avg_power_kw"
                stroke="var(--iv-cyan)"
                strokeWidth={2}
                dot={false}
                name="avg_power_kw"
              />
              <Line
                type="monotone"
                dataKey="max_power_kw"
                stroke="var(--iv-green)"
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
                name="max_power_kw"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Bracket chart — energy + time per SoC bracket */}
      {data.brackets.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-iv-border bg-iv-surface">
          <div className="flex items-center gap-2 border-b border-iv-border px-4 py-3">
            <Zap className="h-5 w-5 text-iv-muted" />
            <h3 className="font-medium text-iv-text">
              Energy &amp; Time by SoC Bracket
            </h3>
          </div>
          <div className="p-4">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart
                data={chartData}
                margin={{ top: 20, right: 30, left: 0, bottom: 5 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  className="stroke-iv-border"
                />
                <XAxis
                  dataKey="name"
                  className="text-iv-muted text-xs"
                />
                <YAxis
                  yAxisId="left"
                  className="text-iv-muted text-xs"
                  label={{
                    value: "kWh",
                    angle: -90,
                    position: "insideLeft",
                    style: { fill: "var(--iv-muted)" },
                  }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  className="text-iv-muted text-xs"
                  label={{
                    value: "min",
                    angle: 90,
                    position: "insideRight",
                    style: { fill: "var(--iv-muted)" },
                  }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--iv-bg)",
                    border: "1px solid var(--iv-border)",
                    borderRadius: "8px",
                  }}
                  itemStyle={{ color: "var(--iv-text)" }}
                />
                <Legend wrapperStyle={{ paddingTop: "16px" }} />
                <Bar
                  yAxisId="left"
                  dataKey="Energy (kWh)"
                  fill="var(--iv-cyan)"
                  radius={[4, 4, 0, 0]}
                />
                <Bar
                  yAxisId="right"
                  dataKey="Time (min)"
                  fill="var(--iv-purple)"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}