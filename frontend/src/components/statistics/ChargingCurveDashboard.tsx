"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine, Area, ComposedChart } from "recharts";
import { Loader2, Zap, Clock, BatteryWarning, TrendingDown } from "lucide-react";
import { api } from "@/lib/api";
import { statisticsApi } from "@/lib/api/statistics";

interface CurvePoint {
  soc_pct: number;
  avg_power_kw: number;
  max_power_kw: number;
  samples: number;
}

interface Metrics {
  wasted_minutes_80_100: number;
  fast_charge_minutes_0_80: number;
  total_charging_minutes: number;
  peak_power_kw?: number;
  avg_power_kw?: number;
}

interface ChargingCurveData {
  curve: CurvePoint[];
  metrics: Metrics;
}

export function ChargingCurveDashboard({ vehicleId, dateRange }: { vehicleId: string; dateRange?: { from: Date; to: Date } }) {
  const [data, setData] = useState<ChargingCurveData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const json = await statisticsApi.getChargingCurveIntegralsV2(vehicleId, {
        fromDate: dateRange?.from?.toISOString(),
        toDate: dateRange?.to?.toISOString(),
      });
      setData(json);
    } catch (err: any) {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [vehicleId, dateRange?.from?.getTime(), dateRange?.to?.getTime()]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Calculate throttle point: where power drops significantly (typically 80% for fast charging)
  const throttlePoint = useMemo(() => {
    if (!data?.curve || data.curve.length < 3) return null;

    const curve = [...data.curve].sort((a, b) => a.soc_pct - b.soc_pct);
    let maxDrop = 0;
    let throttleSoc = 80; // default

    for (let i = 1; i < curve.length; i++) {
      const prevPower = curve[i - 1].avg_power_kw;
      const currPower = curve[i].avg_power_kw;
      if (prevPower > 0) {
        const drop = (prevPower - currPower) / prevPower;
        if (drop > maxDrop && curve[i].soc_pct >= 60) {
          maxDrop = drop;
          throttleSoc = curve[i].soc_pct;
        }
      }
    }

    return {
      soc: throttleSoc,
      power: curve.find(c => c.soc_pct === throttleSoc)?.avg_power_kw || 0
    };
  }, [data?.curve]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-iv-muted" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center py-12 text-iv-muted">
        Failed to load charging curve data.
      </div>
    );
  }

  const peakPower = data.metrics.peak_power_kw || Math.max(...(data.curve.map(c => c.max_power_kw) || [0]));
  const avgPower = data.metrics.avg_power_kw || (data.curve.length > 0 ? data.curve.reduce((sum, c) => sum + c.avg_power_kw, 0) / data.curve.length : 0);

  return (
    <div className="space-y-6">
      <p className="text-sm text-iv-muted">
        Charging power across different battery levels (SoC), highlighting the time spent charging the last 20%.
      </p>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
            <p className="text-xs font-medium text-iv-muted">Time (0-80%)</p>
            <p className="text-2xl font-bold text-iv-text">{data.metrics.fast_charge_minutes_0_80} min</p>
            <p className="text-xs text-iv-muted">avg time per session</p>
          </div>
        </div>

        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-red-500/10 p-4">
          <div className="rounded-lg bg-red-500/15 p-3">
            <TrendingDown className="h-6 w-6 text-red-500" />
          </div>
          <div>
            <p className="text-xs font-medium text-red-400">Time Wasted (80-100%)</p>
            <p className="text-2xl font-bold text-red-400">{data.metrics.wasted_minutes_80_100} min</p>
            <p className="text-xs text-red-400/70">avg time wasted per session</p>
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-iv-border bg-iv-surface">
        <div className="flex items-center gap-2 border-b border-iv-border px-4 py-3">
          <BatteryWarning className="h-5 w-5 text-iv-muted" />
          <h3 className="font-medium text-iv-text">Charging Power Curve</h3>
          {throttlePoint && (
            <span className="ml-auto flex items-center gap-1.5 rounded-full bg-red-500/10 px-3 py-1 text-xs font-medium text-red-400">
              <TrendingDown className="h-3 w-3" />
              Throttle at {throttlePoint.soc}% SoC
            </span>
          )}
        </div>

        {data.curve.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-iv-muted">No curve data available.</div>
        ) : (
          <div className="p-4">
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={data.curve} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                <defs>
                  <linearGradient id="powerGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--iv-cyan)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="var(--iv-cyan)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
                <XAxis
                  dataKey="soc_pct"
                  tick={{ fontSize: 12 }}
                  className="text-iv-muted"
                  label={{ value: "State of Charge (%)", position: "insideBottom", offset: -5 }}
                  domain={[0, 100]}
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  className="text-iv-muted"
                  label={{ value: "Power (kW)", angle: -90, position: "insideLeft" }}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: "var(--iv-bg)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                  labelStyle={{ color: "var(--iv-muted)" }}
                  formatter={(value: number, name: string) => [value.toFixed(2), name === "avg_power_kw" ? "Avg Power (kW)" : "Max Power (kW)"]}
                  labelFormatter={(label) => `SoC: ${label}%`}
                />
                {/* Throttle zone annotation (80-100%) */}
                <ReferenceLine
                  x={80}
                  stroke="var(--iv-red)"
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  label={{
                    value: "80% Throttle",
                    position: "top",
                    fill: "var(--iv-red)",
                    fontSize: 11,
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="avg_power_kw"
                  stroke="none"
                  fill="url(#powerGradient)"
                  name="avg_power_kw"
                />
                <Line
                  type="monotone"
                  dataKey="avg_power_kw"
                  stroke="var(--iv-cyan)"
                  strokeWidth={2}
                  dot={true}
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
              </ComposedChart>
            </ResponsiveContainer>

            {/* Throttle explanation */}
            {throttlePoint && (
              <div className="mt-4 flex items-start gap-3 rounded-lg bg-red-500/10 border border-red-500/20 p-3">
                <TrendingDown className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
                <div className="text-sm">
                  <p className="font-medium text-red-400">
                    Throttle Point Detected at {throttlePoint.soc}% SoC ({throttlePoint.power.toFixed(1)} kW)
                  </p>
                  <p className="text-iv-muted mt-1">
                    Above {throttlePoint.soc}%, charging power drops significantly. This is where most of your
                    &quot;wasted time&quot; comes from — the last 20% takes almost as long as the first 80%.
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
