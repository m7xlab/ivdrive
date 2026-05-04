"use client";

import { useState, useEffect, Component, ReactNode } from "react";
import { api } from "@/lib/api";
import { Loader2, Gauge, AlertTriangle } from "lucide-react";
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

// ── ErrorBoundary: catches render-time React errors ────────────────────────────
interface EBState { hasError: boolean; errorMessage: string }
class ChartErrorBoundary extends Component<{ children: ReactNode }, EBState> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, errorMessage: "" };
  }
  static getDerivedStateFromError(err: Error): EBState {
    return { hasError: true, errorMessage: err.message };
  }
  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="flex items-center gap-2 p-4 text-red-400 text-sm">
          <AlertTriangle size={14} />
          <span>Chart error: {this.state.errorMessage}</span>
        </div>
      );
    }
    return this.props.children;
  }
}

export function SpeedTempMatrixDashboard({ vehicleId }: { vehicleId: string }) {
  const [data, setData] = useState<SpeedTempMatrixResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!vehicleId) return;
    const fetchData = async () => {
      try {
        setLoading(true);
        const res = await api.getSpeedTempMatrix(vehicleId);
        if (process.env.NODE_ENV === "development") {
          console.error(`[SpeedTempMatrix] Received: ${Array.isArray(res.grid) ? res.grid.length : 'N/A'} grid rows`);
        }
        setData(res);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        if (process.env.NODE_ENV === "development") {
          console.error("[SpeedTempMatrix] Fetch failed:", msg);
        }
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

  // Flatten grid for bar chart view
  const chartData = data.grid
    .filter((g) => g.avg_kwh_100km !== null)
    .map((g) => ({
      name: `${g.speed_label} / ${g.temp_label}`,
      avg_kwh_100km: g.avg_kwh_100km,
      trip_count: g.trip_count,
      speed: g.speed_category,
      temp: g.temp_category,
    }));

  // Guard against empty chartData (prevents NaN in getColor)
  if (chartData.length === 0) {
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

  // Get min/max for color scaling
  const allVals = chartData.flatMap((d) => (d.avg_kwh_100km != null ? [d.avg_kwh_100km] : []));
  const minVal = allVals.length > 0 ? Math.min(...allVals) : 0;
  const maxVal = allVals.length > 0 ? Math.max(...allVals) : 1;

  const getColor = (val: number) => {
    if (!val || maxVal === minVal) return "#6b7280";
    const t = (val - minVal) / (maxVal - minVal);
    if (t < 0.5) {
      const r = Math.round(34 + (234 - 34) * t * 2);
      const g = Math.round(197 - 197 * t * 2 + 94 * t * 2);
      const b = Math.round(37 + 37 * t * 2);
      return `rgb(${r},${g},${b})`;
    } else {
      const t2 = (t - 0.5) * 2;
      const r = Math.round(234 + (239 - 234) * t2);
      const g = Math.round(68 - 68 * t2);
      const b = Math.round(68 + 68 * t2);
      return `rgb(${r},${g},${b})`;
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

        {/* Heatmap-style grid as colored bars — wrapped in ErrorBoundary to prevent blank panels */}
        <ChartErrorBoundary>
          <div className="h-80 w-full mb-6">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 20, right: 30, left: 0, bottom: 80 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
                <XAxis dataKey="name" className="text-iv-muted text-xs" angle={-45} textAnchor="end" interval={0} height={70} />
                <YAxis className="text-iv-muted text-xs" label={{ value: 'kWh/100km', angle: -90, position: 'insideLeft', style: { fill: 'var(--iv-muted)' } }} />
                <Tooltip
                  contentStyle={{ backgroundColor: "var(--iv-bg)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                  itemStyle={{ color: "var(--iv-text)" }}
                  formatter={(value: number, name: string, props: any) => [`${value} kWh/100km (${props.payload?.trip_count ?? 0} trips)`, "Efficiency"]}
                />
                <Bar dataKey="avg_kwh_100km" name="kWh/100km" radius={[4, 4, 0, 0]}>
                  {chartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={getColor(entry.avg_kwh_100km ?? 0)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartErrorBoundary>

        {/* Color legend */}
        <div className="flex items-center justify-between text-xs text-iv-text-muted mb-4">
          <span>Best efficiency</span>
          <div className="flex items-center gap-1">
            <div className="w-24 h-3 rounded" style={{ background: "linear-gradient(to right, #22c55e, #eab308, #ef4444)" }} />
          </div>
          <span>Worst efficiency</span>
        </div>

        {/* Matrix as table */}
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
                  {(data.matrix_values[si] ?? []).map((val, ti) => {
                    const count = (data.trip_counts[si] ?? [])[ti] ?? 0;
                    return (
                      <td key={ti} className="text-center p-2">
                        <span
                          className="inline-block px-2 py-1 rounded text-xs font-bold"
                          style={{ backgroundColor: val ? getColor(val) + "33" : "transparent", color: val ? getColor(val) : "var(--iv-muted)" }}
                        >
                          {val ? `${val}` : "—"}
                        </span>
                        {count > 0 && <span className="block text-[10px] text-iv-text-muted">{count} trips</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
