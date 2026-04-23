"use client";

import { useEffect, useState, useCallback } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Loader2, Zap, Clock, BatteryWarning } from "lucide-react";
import { api } from "@/lib/api";

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
    const controller = new AbortController();
    try {
      // Assuming api.fetchWrapper can be used or just use native fetch if not defined
      const token = localStorage.getItem("access_token");
      let url = `/api/v1/vehicles/${vehicleId}/analytics/charging-curve-integrals`;
      if (dateRange?.from && dateRange?.to) {
        url += `?from_date=${dateRange.from.toISOString()}&to_date=${dateRange.to.toISOString()}`;
      }
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal
      });
      if (res.ok) {
        const json = await res.json();
        setData(json);
      } else {
        setData(null);
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setData(null);
      }
    } finally {
      setLoading(false);
    }
    
    return controller;
  }, [vehicleId, dateRange?.from, dateRange?.to]);

  useEffect(() => {
    let activeController: AbortController | null = null;
    fetchData().then(controller => {
      activeController = controller;
    });
    
    return () => {
      if (activeController) {
        activeController.abort();
      }
    };
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

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-iv-surface p-4">
          <div className="rounded-lg bg-iv-cyan/15 p-3">
            <Zap className="h-6 w-6 text-iv-cyan" />
          </div>
          <div>
            <p className="text-xs font-medium text-iv-muted">Fast Charging (0-80%)</p>
            <p className="text-2xl font-bold text-iv-text">{data.metrics.fast_charge_minutes_0_80} min</p>
            <p className="text-xs text-iv-muted">avg time per session</p>
          </div>
        </div>

        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-iv-surface p-4">
          <div className="rounded-lg bg-red-500/15 p-3">
            <Clock className="h-6 w-6 text-red-500" />
          </div>
          <div>
            <p className="text-xs font-medium text-iv-muted">Time Wasted (80-100%)</p>
            <p className="text-2xl font-bold text-red-400">{data.metrics.wasted_minutes_80_100} min</p>
            <p className="text-xs text-iv-muted">avg time wasted per session</p>
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
