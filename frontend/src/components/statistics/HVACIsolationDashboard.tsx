"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Loader2, ThermometerSnowflake, Calculator, TrendingUp } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface HVACMetric {
  speed_profile: string;
  avg_speed_desc: string;
  cold_trips: number;
  optimal_trips: number;
  optimal_kwh_100km: number;
  cold_kwh_100km: number;
  hvac_cost_kwh_100km: number;
  message: string;
}

interface HVACResponse {
  metrics: HVACMetric[];
  summary: string;
}

export function HVACIsolationDashboard({ vehicleId, dateRange }: { vehicleId: string; dateRange?: { from: Date; to: Date } }) {
  const [data, setData] = useState<HVACResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchHVAC = async () => {
      try {
        setLoading(true);
        const opts = dateRange ? { fromDate: dateRange.from.toISOString(), toDate: dateRange.to.toISOString() } : undefined;
        const res = await api.getHVACIsolation(vehicleId, opts);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch HVAC isolation data", err);
      } finally {
        setLoading(false);
      }
    };
    fetchHVAC();
  }, [vehicleId, dateRange?.from?.toISOString(), dateRange?.to?.toISOString()]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 glass rounded-2xl border border-iv-border p-6 mt-6">
        <Loader2 className="h-8 w-8 animate-spin text-iv-muted" />
      </div>
    );
  }

  if (!data || data.metrics.length === 0) {
    return (
      <div className="glass rounded-2xl border border-iv-border p-6 mt-6">
        <div className="flex items-center gap-2 mb-2">
          <ThermometerSnowflake className="h-5 w-5 text-iv-muted" />
          <h3 className="text-lg font-bold text-iv-text">HVAC & Auxiliary Power Isolation</h3>
        </div>
        <p className="text-sm text-iv-text-muted">
          Not enough trips to calculate HVAC costs across temperature brackets.
        </p>
      </div>
    );
  }

  // Format data for Recharts
  const chartData = data.metrics.map((m) => ({
    name: `${m.speed_profile.charAt(0).toUpperCase() + m.speed_profile.slice(1)} (${m.avg_speed_desc})`,
    "Optimal (15-25°C)": m.optimal_kwh_100km,
    "HVAC Cost": m.hvac_cost_kwh_100km,
  }));

  // Calculate overall HVAC cost per degree
  // Using cold threshold of 5°C and optimal range of 15-25°C (20°C delta)
  const avgHvacCost = data.metrics.length > 0
    ? data.metrics.reduce((sum, m) => sum + m.hvac_cost_kwh_100km, 0) / data.metrics.length
    : 0;
  const coldTempThreshold = 5; // °C
  const optimalTempMin = 15; // °C
  const tempDelta = optimalTempMin - coldTempThreshold; // 10°C
  const hvacCostPerDegree = tempDelta > 0 ? avgHvacCost / tempDelta : 0;

  return (
    <div className="space-y-6 mt-6">
      {/* Formula Breakdown Section */}
      <div className="glass rounded-2xl border border-iv-border p-6">
        <div className="flex items-center gap-2 mb-4">
          <Calculator className="h-5 w-5 text-iv-cyan" />
          <h3 className="text-lg font-bold text-iv-text">HVAC Cost Formula Breakdown</h3>
        </div>

        <div className="bg-iv-surface/50 rounded-xl p-4 border border-iv-border">
          <div className="font-mono text-sm space-y-3">
            <div className="flex items-center gap-2 text-iv-text-muted">
              <span className="text-iv-cyan">1.</span>
              <span>Compare cold trips (≤{coldTempThreshold}°C) vs optimal trips (15-25°C)</span>
            </div>
            <div className="flex items-center gap-2 text-iv-text-muted">
              <span className="text-iv-cyan">2.</span>
              <span>Isolate HVAC consumption:</span>
            </div>
            <div className="flex items-center gap-2 ml-6 p-2 bg-iv-bg rounded border border-iv-border/50">
              <span className="text-iv-text">HVAC_cost = cold_eff − optimal_eff</span>
            </div>
            <div className="flex items-center gap-2 text-iv-text-muted">
              <span className="text-iv-cyan">3.</span>
              <span>Per-degree cost calculation:</span>
            </div>
            <div className="flex items-center gap-2 ml-6 p-2 bg-iv-bg rounded border border-iv-border/50">
              <span className="text-iv-text">
                Cost_per_°C = HVAC_cost / {tempDelta}°C (temp delta: {optimalTempMin}°C − {coldTempThreshold}°C)
              </span>
            </div>
          </div>
        </div>

        {/* Summary metric */}
        {hvacCostPerDegree > 0 && (
          <div className="mt-4 flex items-center gap-4 rounded-xl bg-iv-cyan/10 border border-iv-cyan/30 p-4">
            <div className="flex items-center gap-3">
              <TrendingUp className="h-8 w-8 text-iv-cyan" />
              <div>
                <p className="text-xs text-iv-text-muted uppercase tracking-wider">Heating Cost (≤5°C)</p>
                <p className="text-2xl font-bold text-iv-cyan">
                  ~{avgHvacCost.toFixed(1)} kWh/100km
                </p>
              </div>
            </div>
            <div className="ml-auto text-right">
              <p className="text-xs text-iv-text-muted uppercase tracking-wider">Per °C</p>
              <p className="text-xl font-bold text-iv-text">
                ~{hvacCostPerDegree.toFixed(2)} kWh/100km/°C
              </p>
              <p className="text-xs text-iv-muted">
                For {data.metrics[0]?.speed_profile || "mixed"} driving
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Main HVAC Dashboard */}
      <div className="glass rounded-2xl border border-iv-border p-6">
        <div className="flex items-center gap-2 mb-2">
          <ThermometerSnowflake className="h-5 w-5 text-iv-cyan" />
          <h3 className="text-lg font-bold text-iv-text">HVAC & Auxiliary Power Isolation</h3>
        </div>
        <p className="text-sm text-iv-text-muted mb-6">{data.summary}</p>

        <div className="h-80 w-full mb-8">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              margin={{ top: 20, right: 30, left: 0, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
              <XAxis dataKey="name" className="text-iv-muted text-xs" />
              <YAxis className="text-iv-muted text-xs" label={{ value: 'kWh/100km', angle: -90, position: 'insideLeft', style: { fill: 'var(--iv-muted)' } }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--iv-bg)",
                  border: "1px solid var(--iv-border)",
                  borderRadius: "8px",
                }}
                itemStyle={{ color: "var(--iv-text)" }}
              />
              <Legend wrapperStyle={{ paddingTop: "20px" }} />
              <Bar dataKey="Optimal (15-25°C)" stackId="a" fill="var(--iv-green)" radius={[0, 0, 4, 4]} />
              <Bar dataKey="HVAC Cost" stackId="a" fill="var(--iv-cyan)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="flex flex-wrap justify-center gap-6">
          {data.metrics.map((m) => (
            <div
              key={m.speed_profile}
              className="bg-white/5 border border-iv-border rounded-xl p-4 flex flex-col justify-between w-full md:w-[calc(50%-1.5rem)] lg:w-[calc(33.333%-1.5rem)] max-w-md"
            >
              <div>
                <h4 className="text-iv-accent font-semibold mb-3 capitalize">
                  {m.speed_profile} ({m.avg_speed_desc})
                </h4>
                <div className="flex flex-col gap-2 text-sm text-iv-text">
                  <div className="flex justify-between items-center">
                    <span className="text-iv-text-muted">Optimal Consumption:</span>
                    <span className="font-medium">{m.optimal_kwh_100km} kWh</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-iv-text-muted">Cold Consumption:</span>
                    <span className="font-medium">{m.cold_kwh_100km} kWh</span>
                  </div>
                  <div className="flex justify-between items-center font-bold border-t border-iv-border pt-3 mt-1">
                    <span className="text-iv-primary">HVAC Penalty:</span>
                    <span className="text-iv-primary text-lg">
                      +{m.hvac_cost_kwh_100km} kWh/100km
                    </span>
                  </div>
                </div>
              </div>
              <div className="mt-4 pt-4 border-t border-iv-border/50">
                <p className="text-xs text-iv-text-muted italic mb-2">"{m.message}"</p>
                <p className="text-[10px] text-iv-text-muted/50 uppercase tracking-wider">
                  Sample Size: {m.cold_trips} Cold / {m.optimal_trips} Optimal Trips
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
