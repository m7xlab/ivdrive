"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Loader2, Battery, Target, Gauge } from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from "recharts";

interface PredictiveSocResponse {
  current_soc_pct: number;
  current_temp_celsius: number;
  target_distance_km: number;
  estimated_range_km: number;
  predicted_arrival_soc_pct: number;
  confidence_pct: number;
  baseline_consumption_kwh_100km: number;
  energy_needed_kwh: number;
  message: string;
  consumption_by_temp: {
    cold: number | null;
    mild: number | null;
    optimal: number | null;
    hot: number | null;
  };
}

export function PredictiveSocDashboard({ vehicleId }: { vehicleId: string }) {
  const [data, setData] = useState<PredictiveSocResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const res = await api.getPredictiveSoc(vehicleId);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch predictive SOC", err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [vehicleId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 glass rounded-2xl border border-iv-border p-6 mt-6">
        <Loader2 className="h-8 w-8 animate-spin text-iv-muted" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="glass rounded-2xl border border-iv-border p-6 mt-6">
        <div className="flex items-center gap-2 mb-2">
          <Target className="h-5 w-5 text-iv-muted" />
          <h3 className="text-lg font-bold text-iv-text">Predictive Arrival SoC</h3>
        </div>
        <p className="text-sm text-iv-text-muted">No data available for prediction.</p>
      </div>
    );
  }

  const confidenceColor =
    data.confidence_pct >= 70 ? "var(--iv-green)" :
    data.confidence_pct >= 45 ? "var(--iv-yellow)" :
    "var(--iv-red)";

  const socData = [
    { label: "Current SoC", value: data.current_soc_pct, color: "var(--iv-cyan)" },
    { label: "Predicted Arrival", value: data.predicted_arrival_soc_pct, color: confidenceColor },
  ];

  const tempConsumptionData = [
    { temp: "<5°C", label: "Cold", consumption: data.consumption_by_temp.cold, color: "var(--iv-blue)" },
    { temp: "5-15°C", label: "Mild", consumption: data.consumption_by_temp.mild, color: "var(--iv-cyan)" },
    { temp: "15-25°C", label: "Optimal", consumption: data.consumption_by_temp.optimal, color: "var(--iv-green)" },
    { temp: ">25°C", label: "Hot", consumption: data.consumption_by_temp.hot, color: "var(--iv-red)" },
  ].filter((t) => t.consumption !== null && t.consumption !== undefined);

  return (
    <div className="space-y-6 mt-6">
      {/* Main prediction card */}
      <div className="glass rounded-2xl border border-iv-border p-8 text-center">
        <div className="flex items-center justify-center gap-3 mb-4">
          <Battery className="h-8 w-8 text-iv-cyan" />
          <h3 className="text-2xl font-bold text-iv-text">Predictive Arrival SoC</h3>
        </div>

        {/* Big number display */}
        <div className="flex items-center justify-center gap-12 my-8">
          <div>
            <p className="text-xs text-iv-text-muted uppercase tracking-wider mb-2">Current</p>
            <p className="text-4xl font-bold text-iv-cyan">{data.current_soc_pct}%</p>
            <p className="text-xs text-iv-muted mt-1">{data.estimated_range_km} km range</p>
          </div>
          <div className="text-iv-muted text-3xl">→</div>
          <div>
            <p className="text-xs text-iv-text-muted uppercase tracking-wider mb-2">Arrival</p>
            <p className="text-4xl font-bold" style={{ color: confidenceColor }}>
              {data.predicted_arrival_soc_pct}%
            </p>
            <p className="text-xs text-iv-muted mt-1">
              {data.target_distance_km} km trip · {data.current_temp_celsius}°C
            </p>
          </div>
        </div>

        {/* Confidence bar */}
        <div className="max-w-md mx-auto">
          <div className="flex justify-between items-center mb-2">
            <p className="text-xs text-iv-text-muted uppercase tracking-wider">Confidence</p>
            <p className="text-sm font-bold" style={{ color: confidenceColor }}>{data.confidence_pct}%</p>
          </div>
          <div className="w-full h-3 rounded-full bg-iv-surface border border-iv-border overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${data.confidence_pct}%`, backgroundColor: confidenceColor }}
            />
          </div>
        </div>

        {/* Message */}
        <p className="mt-6 text-sm text-iv-text-muted italic">{data.message}</p>

        {/* Consumption breakdown */}
        <div className="mt-6 pt-4 border-t border-iv-border text-left">
          <p className="text-xs text-iv-text-muted uppercase tracking-wider mb-3">Consumption Breakdown</p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-iv-text-muted">Baseline (at {data.current_temp_celsius}°C)</p>
              <p className="text-lg font-bold text-iv-text">{data.baseline_consumption_kwh_100km} kWh/100km</p>
            </div>
            <div>
              <p className="text-xs text-iv-text-muted">Energy Needed</p>
              <p className="text-lg font-bold text-iv-text">{data.energy_needed_kwh} kWh</p>
            </div>
          </div>
        </div>
      </div>

      {/* Consumption by temperature chart */}
      {tempConsumptionData.length > 0 && (
        <div className="glass rounded-2xl border border-iv-border p-6">
          <h3 className="text-lg font-bold text-iv-text mb-4">Consumption by Temperature</h3>
          <div className="h-48 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={tempConsumptionData} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
                <XAxis dataKey="temp" className="text-iv-muted text-xs" />
                <YAxis className="text-iv-muted text-xs" label={{ value: 'kWh/100km', angle: -90, position: 'insideLeft', style: { fill: 'var(--iv-muted)' } }} />
                <Tooltip
                  contentStyle={{ backgroundColor: "var(--iv-bg)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                  itemStyle={{ color: "var(--iv-text)" }}
                  formatter={(value: number) => [`${value} kWh/100km`, "Consumption"]}
                />
                <Bar dataKey="consumption" radius={[4, 4, 0, 0]}>
                  {tempConsumptionData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}