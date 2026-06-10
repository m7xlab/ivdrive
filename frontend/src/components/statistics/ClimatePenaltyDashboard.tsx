"use client";

import { useState, useEffect } from "react";
import { statisticsApi } from "@/lib/api/statistics";
import { Loader2, Sun, Snowflake, Thermometer } from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface ByTempState {
  avg_kwh_100km: number | null;
  trip_count: number;
}
interface ByTempRow {
  temperature: number;
  states: Record<string, ByTempState>;
}
interface ClimatePenaltyResponse {
  vehicle_id: string;
  baseline_kwh_100km: number | null;
  heating_avg_kwh_100km: number | null;
  cooling_avg_kwh_100km: number | null;
  heating_penalty_kwh_100km: number | null;
  cooling_penalty_kwh_100km: number | null;
  trips_heating: number;
  trips_cooling: number;
  trips_off: number;
  min_trips_threshold: number;
  by_temperature: ByTempRow[];
  summary: string;
}

export function ClimatePenaltyDashboard({
  vehicleId,
  dateRange,
}: {
  vehicleId: string;
  dateRange?: { from: Date; to: Date };
}) {
  const [data, setData] = useState<ClimatePenaltyResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchClimate = async () => {
      try {
        setLoading(true);
        const opts = dateRange
          ? { fromDate: dateRange.from.toISOString(), toDate: dateRange.to.toISOString() }
          : undefined;
        const res = await statisticsApi.getClimatePenalty(vehicleId, opts);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch climate penalty data", err);
      } finally {
        setLoading(false);
      }
    };
    fetchClimate();
  }, [vehicleId, dateRange?.from?.toISOString(), dateRange?.to?.toISOString()]);

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
        <p className="text-sm text-iv-text-muted">No climate penalty data available.</p>
      </div>
    );
  }

  const fmt = (v: number | null | undefined) =>
    v === null || v === undefined ? "—" : `${v.toFixed(1)} kWh/100km`;

  // Chart: consumption vs temperature, separate lines per state
  const chartData = data.by_temperature.map((row) => ({
    temperature: row.temperature,
    HEATING: row.states.HEATING?.avg_kwh_100km ?? null,
    COOLING: row.states.COOLING?.avg_kwh_100km ?? null,
    OFF: row.states.OFF?.avg_kwh_100km ?? null,
  }));

  const totalTrips = data.trips_heating + data.trips_cooling + data.trips_off;
  const dataSufficient = data.trips_heating >= data.min_trips_threshold || data.trips_cooling >= data.min_trips_threshold;

  return (
    <div className="space-y-6 mt-6">
      {/* Summary */}
      <div className="glass rounded-2xl border border-iv-border p-6">
        <div className="flex items-center gap-2 mb-2">
          <Thermometer className="h-5 w-5 text-iv-cyan" />
          <h3 className="text-lg font-bold text-iv-text">Climate Penalty Breakdown</h3>
        </div>
        <p className="text-sm text-iv-text-muted mb-1">{data.summary}</p>
        <p className="text-xs text-iv-text-muted/70">
          {totalTrips} trips analyzed: {data.trips_heating} heating, {data.trips_cooling} cooling, {data.trips_off} climate off.{" "}
          Min {data.min_trips_threshold} HVAC-active trips required for a reliable penalty number.
        </p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KPICard
          icon={<Snowflake className="h-5 w-5 text-iv-cyan" />}
          label="Heating Penalty"
          value={fmt(data.heating_penalty_kwh_100km)}
          sublabel={
            data.heating_penalty_kwh_100km === null
              ? `${data.trips_heating} heating trip${data.trips_heating === 1 ? "" : "s"} (need ≥${data.min_trips_threshold})`
              : `vs ${fmt(data.baseline_kwh_100km)} baseline`
          }
          tone={data.heating_penalty_kwh_100km && data.heating_penalty_kwh_100km > 0 ? "penalty" : "neutral"}
        />
        <KPICard
          icon={<Sun className="h-5 w-5 text-amber-400" />}
          label="Cooling Penalty"
          value={fmt(data.cooling_penalty_kwh_100km)}
          sublabel={
            data.cooling_penalty_kwh_100km === null
              ? `${data.trips_cooling} cooling trip${data.trips_cooling === 1 ? "" : "s"} (need ≥${data.min_trips_threshold})`
              : `vs ${fmt(data.baseline_kwh_100km)} baseline`
          }
          tone={data.cooling_penalty_kwh_100km && data.cooling_penalty_kwh_100km > 0 ? "penalty" : "neutral"}
        />
        <KPICard
          icon={<Thermometer className="h-5 w-5 text-iv-text-muted" />}
          label="Baseline (Climate Off)"
          value={fmt(data.baseline_kwh_100km)}
          sublabel={`${data.trips_off} trips — no HVAC active`}
          tone="neutral"
        />
      </div>

      {/* Chart */}
      {chartData.length > 0 ? (
        <div className="glass rounded-2xl border border-iv-border p-6">
          <h4 className="text-sm font-semibold text-iv-text mb-4">
            Consumption by Outside Temperature & HVAC State
          </h4>
          <div className="h-80 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--iv-border)" />
                <XAxis
                  dataKey="temperature"
                  tick={{ fontSize: 12, fill: "var(--iv-text-muted)" }}
                  label={{ value: "Outside °C", position: "insideBottom", offset: -2, style: { fill: "var(--iv-text-muted)", fontSize: 12 } }}
                />
                <YAxis
                  tick={{ fontSize: 12, fill: "var(--iv-text-muted)" }}
                  label={{ value: "kWh/100km", angle: -90, position: "insideLeft", style: { fill: "var(--iv-text-muted)", fontSize: 12 } }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--iv-surface)",
                    border: "1px solid var(--iv-border)",
                    borderRadius: "8px",
                  }}
                  labelStyle={{ color: "var(--iv-text)" }}
                  itemStyle={{ color: "var(--iv-text)" }}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: "var(--iv-text-muted)" }} />
                <Line
                  type="monotone"
                  dataKey="HEATING"
                  stroke="#00D4FF"
                  strokeWidth={2.5}
                  dot={{ r: 3 }}
                  connectNulls
                  name="Heating active"
                />
                <Line
                  type="monotone"
                  dataKey="COOLING"
                  stroke="#f59e0b"
                  strokeWidth={2.5}
                  dot={{ r: 3 }}
                  connectNulls
                  name="Cooling active"
                />
                <Line
                  type="monotone"
                  dataKey="OFF"
                  stroke="var(--iv-green)"
                  strokeWidth={2}
                  dot={{ r: 2 }}
                  strokeDasharray="4 4"
                  connectNulls
                  name="Climate off (baseline)"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          {!dataSufficient && (
            <p className="text-xs text-iv-text-muted italic mt-3">
              Penalty numbers suppressed when sample size is small — more trips with active climate will give a reliable number.
            </p>
          )}
        </div>
      ) : (
        <div className="glass rounded-2xl border border-iv-border p-6 text-center">
          <p className="text-sm text-iv-text-muted">
            No trips with matching climate state data in the selected period.
          </p>
        </div>
      )}
    </div>
  );
}

function KPICard({
  icon,
  label,
  value,
  sublabel,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sublabel: string;
  tone: "penalty" | "neutral";
}) {
  const accent =
    tone === "penalty"
      ? "border-iv-danger/30 bg-iv-danger/5"
      : "border-iv-border";
  return (
    <div className={`rounded-2xl border p-5 ${accent}`}>
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <h4 className="text-xs uppercase tracking-wider text-iv-text-muted font-semibold">
          {label}
        </h4>
      </div>
      <p className="text-3xl font-bold text-iv-text mb-1">{value}</p>
      <p className="text-xs text-iv-text-muted">{sublabel}</p>
    </div>
  );
}
