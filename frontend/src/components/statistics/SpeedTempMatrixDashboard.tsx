"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Loader2, Gauge } from "lucide-react";
import {
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

interface SpeedTempMatrixResponse {
  grid: Array<{
    speed_category: string;
    speed_label: string;
    temp_category: string;
    temp_label: string;
    avg_kwh_100km: number | null;
    trip_count: number;
  }>;
  speed_categories: string[];
  temp_categories: string[];
  matrix_values: (number | null)[][];
  trip_counts: number[][];
}

export function SpeedTempMatrixDashboard({ vehicleId }: { vehicleId: string }) {
  const [data, setData] = useState<SpeedTempMatrixResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const res = await api.getSpeedTempMatrix(vehicleId);
        console.error("[SpeedTempMatrix] raw response:", res);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch speed-temp matrix", err);
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

  if (!data || data.grid.length === 0) {
    return (
      <div className="glass rounded-2xl border border-iv-border p-6 mt-6">
        <div className="flex items-center gap-2 mb-2">
          <Gauge className="h-5 w-5 text-iv-muted" />
          <h3 className="text-lg font-bold text-iv-text">Ideal Cruising Speed Matrix</h3>
        </div>
        <p className="text-sm text-iv-text-muted">Not enough trip data for speed/temperature matrix.</p>
      </div>
    );
  }

  // Flatten grid for bar chart view — use null coalescing for safety
  const chartData = data.grid
    .filter((g) => g.avg_kwh_100km != null)
    .map((g) => ({
      name: `${g.speed_label} / ${g.temp_label}`,
      avg_kwh_100km: g.avg_kwh_100km as number,
      trip_count: g.trip_count,
      speed: g.speed_category,
      temp: g.temp_category,
    }));

  // Get min/max for color scaling (guard against empty chartData)
  const allVals = chartData.flatMap((d) => [d.avg_kwh_100km]);
  const minVal = allVals.length > 0 ? Math.min(...allVals) : 0;
  const maxVal = allVals.length > 0 ? Math.max(...allVals) : 1;
  const getColor = (val: number | null | undefined): string => {
    if (val == null) return "#6b7280";
    if (val === 0) return "#6b7280";
    if (maxVal === minVal) return "#6b7280";
    const t = (val - minVal) / (maxVal - minVal);
    // green (best) → yellow → red (worst)
    if (t < 0.5) {
      const r = Math.round(34 + (234 - 34) * t * 2);
      const gv = Math.round(197 - 197 * t * 2 + 94 * t * 2);
      const b = Math.round(37 + 37 * t * 2);
      return `rgb(${r},${gv},${b})`;
    } else {
      const t2 = (t - 0.5) * 2;
      const r = Math.round(234 + (239 - 234) * t2);
      const gv = Math.round(68 - 68 * t2);
      const b = Math.round(68 + 68 * t2);
      return `rgb(${r},${gv},${b})`;
    }
  };

  return (
    <div className="space-y-6 mt-6">
      <div className="glass rounded-2xl border border-iv-border p-6">
        <div className="flex items-center gap-2 mb-2">
          <Gauge className="h-5 w-5 text-iv-cyan" />
          <h3 className="text-lg font-bold text-iv-text">Ideal Cruising Speed Matrix</h3>
        </div>
        <p className="text-sm text-iv-text-muted mb-6">
          Average consumption (kWh/100km) by Speed Category × Temperature. Green = best efficiency.
        </p>

        {/* Heatmap-style grid as colored bars */}
        <ErrorBoundary>
        <div className="h-80 w-full mb-6">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 20, right: 30, left: 0, bottom: 80 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
              <XAxis dataKey="name" className="text-iv-muted text-xs" angle={-45} textAnchor="end" interval={0} height={70} />
              <YAxis className="text-iv-muted text-xs" label={{ value: 'kWh/100km', angle: -90, position: 'insideLeft', style: { fill: 'var(--iv-muted)' } }} />
              <Tooltip
                contentStyle={{ backgroundColor: "var(--iv-bg)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                itemStyle={{ color: "var(--iv-text)" }}
              />
              <Bar dataKey="avg_kwh_100km" name="kWh/100km" radius={[4, 4, 0, 0]}>
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={getColor(entry.avg_kwh_100km ?? null)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        </ErrorBoundary>

        {/* Color legend */}
        <ErrorBoundary>
        <div className="flex items-center justify-between text-xs text-iv-text-muted mb-4">
          <span>Best efficiency</span>
          <div className="flex items-center gap-1">
            <div className="w-24 h-3 rounded" style={{ background: "linear-gradient(to right, #22c55e, #eab308, #ef4444)" }} />
          </div>
          <span>Worst efficiency</span>
        </div>
        </ErrorBoundary>

        {/* Matrix as table */}
        <ErrorBoundary>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                <th className="text-left text-iv-text-muted p-2">Speed ↓ / Temp →</th>
                {data.temp_categories.map((tc) => (
                  <th key={tc} className="text-center text-iv-text p-2">{tc}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.speed_categories.map((sc, si) => (
                <tr key={sc} className="border-t border-iv-border">
                  <td className="text-iv-text-muted p-2 font-medium">{sc}</td>
                  {data.matrix_values[si].map((val, ti) => {
                    const count = data.trip_counts[si][ti];
                    return (
                      <td key={ti} className="text-center p-2">
                        <span
                          className="inline-block px-2 py-1 rounded text-xs font-bold"
                          style={{ backgroundColor: val != null ? getColor(val) + "33" : "transparent", color: val != null ? getColor(val) : "var(--iv-muted)" }}
                        >
                          {val != null ? `${val}` : "—"}
                        </span>
                        {count != null && count > 0 && <span className="block text-[10px] text-iv-text-muted">{count} trips</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </ErrorBoundary>
      </div>
    </div>
  );
}