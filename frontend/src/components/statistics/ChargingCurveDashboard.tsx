"use client";

import { useEffect, useState, useCallback } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Loader2, Zap, Clock, BatteryWarning } from "lucide-react";
import { statisticsApi } from "@/lib/api/statistics";
import { formatSmartDuration } from "@/lib/format";

interface CurvePoint {
  soc_pct: number;
  avg_power_kw: number;
  max_power_kw: number;
  samples: number;
}

interface ChargingCurveData {
  curve: CurvePoint[];
  brackets: Array<{ label: string; energy_kwh: number; minutes: number; samples: number }>;
  wasted_minutes_80_100: number;
  total_energy_kwh: number;
  total_minutes: number;
  wasted_pct: number;
  message?: string;
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
            <p className="text-2xl font-bold text-iv-text">
              {data.curve.length > 0 ? Math.max(...data.curve.map(p => p.max_power_kw)).toFixed(1) : 0} kW
            </p>
            <p className="text-xs text-iv-muted">max observed</p>
          </div>
        </div>

        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-iv-surface p-4">
          <div className="rounded-lg bg-iv-cyan/15 p-3">
            <Zap className="h-6 w-6 text-iv-cyan" />
          </div>
          <div>
            <p className="text-xs font-medium text-iv-muted">Avg Power</p>
            <p className="text-2xl font-bold text-iv-text">
              {data.curve.length > 0
                ? (data.curve.reduce((s, p) => s + p.avg_power_kw, 0) / data.curve.length).toFixed(1)
                : 0} kW
            </p>
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
            <p className="text-xs text-iv-muted">{data.total_energy_kwh.toFixed(1)} kWh added</p>
          </div>
        </div>

        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-iv-surface p-4">
          <div className="rounded-lg bg-red-500/15 p-3">
            <Clock className="h-6 w-6 text-red-500" />
          </div>
          <div>
            <p className="text-xs font-medium text-iv-muted">Time Wasted (80-100%)</p>
            <p className="text-2xl font-bold text-red-400">{formatSmartDuration(data.wasted_minutes_80_100)}</p>
            <p className="text-xs text-iv-muted">{data.wasted_pct}% of total</p>
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-iv-border bg-iv-surface">
        <div className="flex items-center gap-2 border-b border-iv-border px-4 py-3">
          <BatteryWarning className="h-5 w-5 text-iv-muted" />
          <h3 className="font-medium text-iv-text">Charging Power Curve</h3>
        </div>
        
        {data.curve.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-iv-muted">No curve data available.</div>
        ) : (
          <div className="p-4">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={data.curve} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
                <XAxis dataKey="soc_pct" tick={{ fontSize: 12 }} className="text-iv-muted" label={{ value: "State of Charge (%)", position: "insideBottom", offset: -5 }} />
                <YAxis tick={{ fontSize: 12 }} className="text-iv-muted" label={{ value: "Power (kW)", angle: -90, position: "insideLeft" }} />
                <Tooltip
                  contentStyle={{ backgroundColor: "var(--iv-bg)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                  labelStyle={{ color: "var(--iv-muted)" }}
                  formatter={(value: number, name: string) => [value.toFixed(2), name === "avg_power_kw" ? "Avg Power (kW)" : "Max Power (kW)"]}
                  labelFormatter={(label) => `SoC: ${label}%`}
                />
                <Line type="monotone" dataKey="avg_power_kw" stroke="var(--iv-cyan)" strokeWidth={2} dot={false} name="avg_power_kw" />
                <Line type="monotone" dataKey="max_power_kw" stroke="var(--iv-green)" strokeWidth={2} strokeDasharray="5 5" dot={false} name="max_power_kw" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}
