"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { format, parseISO, getYear, getMonth } from "date-fns";
import {
  Loader2, Route, Zap, BatteryCharging, Timer, Calendar,
  Car, ParkingSquare, Zap as ZapIcon, KeyRound, WifiOff,
  MapPin, Clock, TrendingUp
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar,
} from "recharts";
import { api } from "@/lib/api";
import type { TimelineRange } from "./StatisticsShell";
import { formatSmartDuration } from "@/lib/format";

export interface DrivingSummaryDashboardProps {
  vehicleId: string;
  dateRange?: TimelineRange;
}

// ── Types ────────────────────────────────────────────────────────────────────

interface StatisticsRow {
  period: string;
  drives_count: number;
  total_distance_km: number;
  time_driven_seconds: number;
  median_distance_km: number | null;
  charging_sessions_count: number;
  total_energy_kwh: number;
  total_kwh_consumed: number;
  time_charging_seconds: number;
}

interface TripAnalyticsItem {
  id: number;
  start_time: string;
  end_time: string | null;
  distance_km: number;
  duration_minutes: number | null;
  kwh_used: number | null;
  start_latitude: number | null;
  start_longitude: number | null;
  destination_latitude: number | null;
  destination_longitude: number | null;
  charging_time_minutes: number | null;
}

interface OdometerItem {
  captured_at: string;
  mileage_in_km: number;
}

interface TimeBudget {
  parked_seconds: number;
  driving_seconds: number;
  charging_seconds: number;
  ignition_seconds: number;
  offline_seconds: number;
}

interface VisitedLocation {
  latitude: number;
  longitude: number;
  timestamp: string;
  source: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDuration(seconds: number): string {
  if (seconds <= 0 || !Number.isFinite(seconds)) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${Math.round(seconds)}s`;
}

function formatPeriodLabel(iso: string, period: string): string {
  try {
    const d = parseISO(iso.replace("Z", "+00:00"));
    switch (period) {
      case "year": return format(d, "yyyy");
      case "month": return format(d, "MMM yyyy");
      case "week": return `W${format(d, "I")}`;
      default: return format(d, "d MMM");
    }
  } catch { return iso; }
}

// ── Component ─────────────────────────────────────────────────────────────────

export function DrivingSummaryDashboard({ vehicleId, dateRange }: DrivingSummaryDashboardProps) {
  // ── State ──────────────────────────────────────────────────────────────────
  const [trips, setTrips] = useState<TripAnalyticsItem[]>([]);
  const [stats, setStats] = useState<StatisticsRow[]>([]);
  const [odometer, setOdometer] = useState<OdometerItem[]>([]);
  const [timeBudget, setTimeBudget] = useState<TimeBudget | null>(null);
  const [visitedLocations, setVisitedLocations] = useState<VisitedLocation[]>([]);
  const [loading, setLoading] = useState(true);

  // ── Fetch all data in parallel ─────────────────────────────────────────────
  const fromISO = dateRange?.from?.toISOString() ?? undefined;
  const toISO = dateRange?.to?.toISOString() ?? undefined;

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [
        tripsData,
        statsData,
        odometerData,
        budgetData,
        locationsData,
      ] = await Promise.allSettled([
        api.getTripsAnalytics(vehicleId, 200, fromISO, toISO),
        api.getStatistics(vehicleId, "day", 30, fromISO, toISO),
        api.getOdometer(vehicleId, 5000, fromISO, toISO),
        api.getTimeBudget(vehicleId),
        api.getVisitedLocations(vehicleId, 2000, fromISO, toISO),
      ]);

      setTrips(tripsData.status === "fulfilled" ? (tripsData.value ?? []) : []);
      setStats(statsData.status === "fulfilled" ? (statsData.value ?? []) : []);
      setOdometer(odometerData.status === "fulfilled" ? (odometerData.value ?? []) : []);
      setTimeBudget(budgetData.status === "fulfilled" ? budgetData.value : null);
      setVisitedLocations(locationsData.status === "fulfilled" ? (locationsData.value ?? []) : []);
    } catch {
      // swallow
    } finally {
      setLoading(false);
    }
  }, [vehicleId, fromISO, toISO]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ── Derived ─────────────────────────────────────────────────────────────────

  // Latest stats row (most recent day)
  const latestStats = stats.length > 0 ? stats[0] : null;

  // Historical stats (last 7 days, skip today)
  const historicalStats = stats.length > 1 ? stats.slice(1, 8) : [];

  // KPI values
  const totalDistance = latestStats ? latestStats.total_distance_km.toFixed(1) : "—";
  const totalDrives = latestStats ? String(latestStats.drives_count) : "—";
  const energyUsed = latestStats ? latestStats.total_kwh_consumed.toFixed(1) : "—";
  const efficiency = (latestStats && latestStats.total_distance_km > 0 && latestStats.total_kwh_consumed > 0)
    ? ((latestStats.total_kwh_consumed / latestStats.total_distance_km) * 100).toFixed(1)
    : "—";

  // Mileage trend chart data (last 30 odometer readings reversed)
  const mileageChartData = useMemo(() => {
    return [...odometer]
      .reverse()
      .slice(0, 30)
      .map((o) => ({
        date: format(parseISO(o.captured_at), "d MMM"),
        km: o.mileage_in_km,
      }));
  }, [odometer]);

  // Time budget
  const tb = timeBudget;
  const totalS = tb
    ? Math.max(
        tb.parked_seconds + tb.driving_seconds + tb.charging_seconds +
        tb.ignition_seconds + tb.offline_seconds,
        1,
      )
    : 1;

  const timeBudgetBuckets = tb
    ? [
        { label: "Parked",    seconds: tb.parked_seconds,   barColor: "bg-iv-text-muted/50", textColor: "text-iv-text",  icon: <ParkingSquare size={14} className="text-iv-muted" /> },
        { label: "Driving",   seconds: tb.driving_seconds,  barColor: "bg-iv-cyan",          textColor: "text-iv-cyan",  icon: <Car size={14} className="text-iv-cyan" /> },
        { label: "Charging",   seconds: tb.charging_seconds, barColor: "bg-iv-green",         textColor: "text-iv-green", icon: <ZapIcon size={14} className="text-iv-green" /> },
        { label: "Ignition",   seconds: tb.ignition_seconds, barColor: "bg-yellow-500/70",    textColor: "text-yellow-400", icon: <KeyRound size={14} className="text-yellow-400" /> },
        { label: "Offline",    seconds: tb.offline_seconds,  barColor: "bg-iv-border",        textColor: "text-iv-muted", icon: <WifiOff size={14} className="text-iv-muted" /> },
      ]
    : [];

  // Top places from visited locations
  const topPlaces = useMemo(() => {
    const map = new Map<string, { lat: number; lon: number; ms: number; count: number }>();
    for (const loc of visitedLocations) {
      const key = `${loc.latitude.toFixed(3)},${loc.longitude.toFixed(3)}`;
      const existing = map.get(key);
      if (existing) { existing.count++; existing.ms += 60000; }
      else map.set(key, { lat: loc.latitude, lon: loc.longitude, ms: 60000, count: 1 });
    }
    return [...map.values()].sort((a, b) => b.ms - a.ms).slice(0, 5);
  }, [visitedLocations]);

  // Recent trips (last 10)
  const recentTrips = useMemo(() => {
    return [...trips].sort((a, b) => {
      const da = new Date(a.start_time).getTime();
      const db = new Date(b.start_time).getTime();
      return db - da;
    }).slice(0, 10);
  }, [trips]);

  // ── Render ──────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-iv-muted" />
      </div>
    );
  }

  const hasData = latestStats || odometer.length > 0 || trips.length > 0;

  if (!hasData) {
    return (
      <div className="py-24 text-center text-sm text-iv-muted">
        No driving data for the selected period.
      </div>
    );
  }

  return (
    <div className="space-y-6">

      {/* ── KPI Row ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="glass rounded-xl p-4 space-y-1">
          <div className="flex items-center gap-2">
            <Route size={14} className="text-iv-cyan" />
            <span className="text-[10px] font-semibold text-iv-muted uppercase tracking-wide">Distance</span>
          </div>
          <p className="text-2xl font-bold text-iv-text">{totalDistance} <span className="text-sm font-normal text-iv-muted">km</span></p>
          {latestStats && <p className="text-xs text-iv-muted">{latestStats.drives_count} drives</p>}
        </div>

        <div className="glass rounded-xl p-4 space-y-1">
          <div className="flex items-center gap-2">
            <Zap size={14} className="text-iv-green" />
            <span className="text-[10px] font-semibold text-iv-muted uppercase tracking-wide">Energy Used</span>
          </div>
          <p className="text-2xl font-bold text-iv-text">{energyUsed} <span className="text-sm font-normal text-iv-muted">kWh</span></p>
        </div>

        <div className="glass rounded-xl p-4 space-y-1">
          <div className="flex items-center gap-2">
            <BatteryCharging size={14} className="text-iv-blue" />
            <span className="text-[10px] font-semibold text-iv-muted uppercase tracking-wide">Charged</span>
          </div>
          <p className="text-2xl font-bold text-iv-text">
            {latestStats ? latestStats.total_energy_kwh.toFixed(1) : "—"} <span className="text-sm font-normal text-iv-muted">kWh</span>
          </p>
          {latestStats && <p className="text-xs text-iv-muted">{latestStats.charging_sessions_count} sessions</p>}
        </div>

        <div className="glass rounded-xl p-4 space-y-1">
          <div className="flex items-center gap-2">
            <TrendingUp size={14} className="text-iv-purple" />
            <span className="text-[10px] font-semibold text-iv-muted uppercase tracking-wide">Efficiency</span>
          </div>
          <p className="text-2xl font-bold text-iv-text">{efficiency} <span className="text-sm font-normal text-iv-muted">kWh/100km</span></p>
        </div>
      </div>

      {/* ── Mileage Trend ── */}
      {mileageChartData.length > 1 && (
        <div className="glass rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-iv-text">Mileage Trend</h3>
            <span className="text-xs bg-iv-surface border border-iv-border text-iv-muted px-2 py-0.5 rounded-full">Last 30 readings</span>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={mileageChartData} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} className="text-iv-muted" tickLine={false} />
              <YAxis tick={{ fontSize: 11 }} className="text-iv-muted" tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ backgroundColor: "var(--iv-bg)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                labelStyle={{ color: "var(--iv-muted)" }}
                formatter={(value: number) => [`${value.toFixed(0)} km`, "Odometer"]}
              />
              <Line type="monotone" dataKey="km" stroke="var(--iv-cyan)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── Time Budget (all-time) ── */}
      {timeBudgetBuckets.length > 0 && (
        <div className="glass rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-iv-text">Time Budget</h3>
            <span className="text-xs bg-iv-surface border border-iv-border text-iv-muted px-2 py-0.5 rounded-full">All-time</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {timeBudgetBuckets.map((b) => (
              <div key={b.label} className="bg-iv-surface/60 rounded-xl p-3 border border-iv-border/50 space-y-1">
                <div className="flex items-center gap-1.5">
                  {b.icon}
                  <span className="text-[10px] font-semibold text-iv-muted uppercase">{b.label}</span>
                </div>
                <p className={`text-xl font-bold ${b.textColor}`}>{formatDuration(b.seconds)}</p>
                <p className="text-xs text-iv-muted">{((b.seconds / totalS) * 100).toFixed(1)}%</p>
              </div>
            ))}
          </div>
          {/* Stacked bar */}
          <div className="flex rounded-full overflow-hidden h-2.5 gap-px bg-iv-border/30">
            {timeBudgetBuckets.map((b) => (
              <div
                key={b.label}
                className={b.barColor}
                style={{ width: `${(b.seconds / totalS) * 100}%` }}
                title={`${b.label}: ${formatDuration(b.seconds)}`}
              />
            ))}
          </div>
        </div>
      )}

      {/* ── Two-column: Recent Trips + Top Places ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Recent Trips */}
        <div className="glass rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-iv-text">Recent Trips</h3>
          {recentTrips.length === 0 ? (
            <p className="text-sm text-iv-muted py-6 text-center">No trips recorded</p>
          ) : (
            <div className="space-y-1.5 max-h-72 overflow-y-auto no-scrollbar">
              {recentTrips.map((trip) => {
                const eff = trip.distance_km > 0 && trip.kwh_used != null && trip.kwh_used > 0
                  ? ((trip.kwh_used / trip.distance_km) * 100).toFixed(1)
                  : "—";
                return (
                  <div key={trip.id} className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-iv-surface/40 hover:bg-iv-surface/70 transition-colors">
                    <div className="p-1.5 rounded-full bg-iv-cyan/10 shrink-0">
                      <Car size={12} className="text-iv-cyan" />
                    </div>
                    <div className="flex-1 min-w-0 grid grid-cols-3 gap-2">
                      <div>
                        <p className="text-xs text-iv-muted">Date</p>
                        <p className="text-sm font-medium text-iv-text truncate">
                          {format(parseISO(trip.start_time), "d MMM HH:mm")}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-iv-muted">Distance</p>
                        <p className="text-sm font-medium text-iv-text">{trip.distance_km.toFixed(1)} km</p>
                      </div>
                      <div>
                        <p className="text-xs text-iv-muted">Efficiency</p>
                        <p className="text-sm font-medium text-iv-text">{eff} kWh/100km</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Top Places */}
        <div className="glass rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-iv-text">Top Places</h3>
          {topPlaces.length === 0 ? (
            <p className="text-sm text-iv-muted py-6 text-center">No places detected</p>
          ) : (
            <div className="space-y-2">
              {topPlaces.map((place, i) => (
                <div key={i} className="flex items-center gap-3 p-3 rounded-xl bg-iv-surface/40 border border-iv-border/30">
                  <div className="p-2 rounded-full bg-iv-cyan/10 shrink-0">
                    <MapPin size={14} className="text-iv-cyan" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-iv-text">{place.lat.toFixed(3)}, {place.lon.toFixed(3)}</p>
                    <p className="text-xs text-iv-muted">{place.count} visits</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Historical Stats ── */}
      {historicalStats.length > 0 && (
        <div className="glass rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-iv-text flex items-center gap-2">
            <Calendar size={14} /> Historical Driving Data
          </h3>
          <div className="space-y-1.5">
            {historicalStats.map((row) => (
              <div key={row.period} className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-iv-surface/30 border border-iv-border/20">
                <div className="p-1.5 rounded-full bg-iv-cyan/10 shrink-0">
                  <Clock size={12} className="text-iv-cyan" />
                </div>
                <div className="flex-[2] min-w-0">
                  <p className="text-sm font-medium text-iv-text">{formatPeriodLabel(row.period, "day")}</p>
                </div>
                <div className="flex-1 text-right">
                  <p className="text-xs text-iv-muted">Distance</p>
                  <p className="text-sm font-medium text-iv-text">{row.total_distance_km.toFixed(1)} km</p>
                </div>
                <div className="flex-1 text-right">
                  <p className="text-xs text-iv-muted">Energy</p>
                  <p className="text-sm font-medium text-iv-text">{row.total_kwh_consumed.toFixed(1)} kWh</p>
                </div>
                <div className="flex-1 text-right">
                  <p className="text-xs text-iv-muted">Drives</p>
                  <p className="text-sm font-medium text-iv-text">{row.drives_count}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}