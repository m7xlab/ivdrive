"use client";

import { useEffect, useState, useCallback } from "react";
import { format, addDays, subDays } from "date-fns";
import { Gauge, Loader2, TrendingUp } from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { api } from "@/lib/api";
import type { TimelineRange } from "./StatisticsShell";
import { formatSmartDuration } from "@/lib/format";

export interface MileageKMDashboardProps {
  vehicleId: string;
  dateRange: TimelineRange;
}

interface OdometerItem {
  captured_at: string;
  mileage_in_km: number;
}

interface StatisticsRow {
  period: string;
  drives_count: number;
  total_distance_km: number;
  time_driven_seconds: number;
  median_distance_km: number | null;
  charging_sessions_count: number;
  total_energy_kwh: number;
  time_charging_seconds: number;
}

function toISO(d: Date) {
  return d.toISOString();
}

/** Simple linear regression: returns [slope, intercept] for y = slope * x + intercept (x in ms). */
function linearRegression(
  points: { x: number; y: number }[]
): { slope: number; intercept: number } | null {
  if (points.length < 2) return null;
  const n = points.length;
  let sumX = 0,
    sumY = 0,
    sumXY = 0,
    sumXX = 0;
  for (const p of points) {
    sumX += p.x;
    sumY += p.y;
    sumXY += p.x * p.y;
    sumXX += p.x * p.x;
  }
  const denom = n * sumXX - sumX * sumX;
  if (denom === 0) return null;
  const slope = (n * sumXY - sumX * sumY) / denom;
  const intercept = (sumY - slope * sumX) / n;
  return { slope, intercept };
}

const FORECAST_DAYS = 90;
const STATS_LOOKBACK_DAYS = 90;

export function MileageKMDashboard({ vehicleId, dateRange }: MileageKMDashboardProps) {
  const [odometer, setOdometer] = useState<OdometerItem[]>([]);
  const [statsDaily, setStatsDaily] = useState<StatisticsRow[]>([]);
  const [loading, setLoading] = useState(true);

  const fromISO = toISO(dateRange.from);
  const toISOVal = toISO(dateRange.to);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const now = new Date();
      const statsFrom = toISO(subDays(now, STATS_LOOKBACK_DAYS));
      const statsTo = toISO(now);
      const [list, stats] = await Promise.all([
        api.getOdometer(vehicleId, 10000, fromISO, toISOVal),
        api.getStatistics(vehicleId, "day", STATS_LOOKBACK_DAYS, statsFrom, statsTo),
      ]);
      setOdometer(list ?? []);
      setStatsDaily(Array.isArray(stats) ? stats : []);
    } catch {
      setOdometer([]);
      setStatsDaily([]);
    } finally {
      setLoading(false);
    }
  }, [vehicleId, fromISO, toISOVal]);

  useEffect(() => {
    fetchData();
    const isLive = !toISOVal || new Date(toISOVal) >= new Date();
    if (!isLive) return;

    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData, toISOVal]);

  if (loading) {
    return (
      <div className="glass rounded-xl p-12 flex flex-col items-center justify-center gap-3">
        <Loader2 className="h-10 w-10 animate-spin text-iv-muted" />
        <p className="text-sm text-iv-muted">Loading mileage data...</p>
      </div>
    );
  }

  if (odometer.length === 0) {
    return (
      <div className="glass rounded-xl p-12 text-center">
        <Gauge size={32} className="mx-auto mb-3 text-iv-muted" />
        <p className="text-sm text-iv-muted">No odometer data for this period.</p>
      </div>
    );
  }

  const sorted = [...odometer].sort(
    (a, b) => new Date(a.captured_at).getTime() - new Date(b.captured_at).getTime()
  );
  const lastOdometerKm = sorted[sorted.length - 1].mileage_in_km;
  const lastOdometerTime = new Date(sorted[sorted.length - 1].captured_at);

  const actualData = sorted.map((o) => ({
    time: o.captured_at,
    label: format(new Date(o.captured_at), "d MMM yyyy"),
    mileage: o.mileage_in_km,
    forecast: null as number | null,
  }));

  const points = sorted.map((o) => ({
    x: new Date(o.captured_at).getTime(),
    y: o.mileage_in_km,
  }));
  const regression = linearRegression(points);

  // Usage-based forecast: average daily distance from Driving Statistics (per day)
  const totalKmOverPeriod =
    statsDaily.length > 0
      ? statsDaily.reduce((sum, r) => sum + r.total_distance_km, 0)
      : 0;
  const avgDailyKm =
    statsDaily.length > 0 ? totalKmOverPeriod / statsDaily.length : 0;
  const daysWithDistance = statsDaily.filter((r) => r.total_distance_km > 0);
  const useUsageModel = avgDailyKm > 0 && daysWithDistance.length >= 3;

  const forecastPoints: Array<{ time: string; label: string; mileage: number | null; forecast: number | null }> = [];
  if (useUsageModel) {
    forecastPoints.push({
      time: lastOdometerTime.toISOString(),
      label: format(lastOdometerTime, "d MMM yyyy"),
      mileage: null,
      forecast: Math.round(lastOdometerKm),
    });
    for (let i = 1; i <= FORECAST_DAYS; i += 7) {
      const t = addDays(lastOdometerTime, i);
      const predicted = lastOdometerKm + avgDailyKm * i;
      forecastPoints.push({
        time: t.toISOString(),
        label: format(t, "d MMM yyyy"),
        mileage: null,
        forecast: Math.round(predicted),
      });
    }
  } else if (regression) {
    const lastPoint = points[points.length - 1];
    const endTime = new Date(lastPoint.x);
    const connectValue = Math.round(regression.slope * lastPoint.x + regression.intercept);
    forecastPoints.push({
      time: endTime.toISOString(),
      label: format(endTime, "d MMM yyyy"),
      mileage: null,
      forecast: connectValue,
    });
    for (let i = 1; i <= FORECAST_DAYS; i += 7) {
      const t = addDays(endTime, i);
      const tMs = t.getTime();
      const predicted = regression.slope * tMs + regression.intercept;
      forecastPoints.push({
        time: t.toISOString(),
        label: format(t, "d MMM yyyy"),
        mileage: null,
        forecast: Math.round(predicted),
      });
    }
  }

  const combinedData = [
    ...actualData,
    ...forecastPoints,
  ].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());

  const forecastCaption = useUsageModel
    ? `Forecast from average daily distance (${avgDailyKm.toFixed(1)} km/day over the last ${statsDaily.length} days); cyan dashed = next ${FORECAST_DAYS} days.`
    : regression
      ? `Forecast: linear trend over the last ${points.length} readings (no daily stats yet); cyan dashed = next ${FORECAST_DAYS} days.`
      : null;

  return (
    <div className="space-y-6">
      <div className="glass rounded-xl p-5">
        <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2">
          <Gauge size={14} /> Mileage (km)
        </h3>
        <div className="h-[320px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={combinedData}
              margin={{ top: 8, right: 8, left: 8, bottom: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--iv-border)" opacity={0.5} />
              <XAxis
                dataKey="time"
                tickFormatter={(v) => format(new Date(v), "d MMM")}
                stroke="#8b8fa3"
                fontSize={11}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                stroke="#8b8fa3"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                domain={["auto", "auto"]}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const p = payload[0].payload;
                  const value = p.mileage ?? p.forecast;
                  const isForecast = p.mileage == null && p.forecast != null;
                  return (
                    <div className="rounded-lg bg-iv-charcoal border border-iv-border px-3 py-2 shadow-xl">
                      <p className="text-xs text-iv-muted">{p.label}</p>
                      <p className="text-sm font-semibold text-iv-text">
                        {value != null ? value.toLocaleString() : "—"} km
                        {isForecast ? (
                          <span className="ml-2 text-iv-cyan text-xs">(forecast)</span>
                        ) : null}
                      </p>
                    </div>
                  );
                }}
              />
              <Line
                type="monotone"
                dataKey="mileage"
                name="Mileage"
                stroke="#4BA82E"
                strokeWidth={2}
                dot={{ r: 3 }}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="forecast"
                name="Forecast"
                stroke="#00D4FF"
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={{ r: 2 }}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
        {forecastCaption && (
          <p className="text-xs text-iv-muted mt-3 flex items-center gap-1">
            <TrendingUp size={12} />
            {forecastCaption}
          </p>
        )}
      </div>
    </div>
  );
}
