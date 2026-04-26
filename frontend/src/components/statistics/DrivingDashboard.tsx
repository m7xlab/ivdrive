"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { format, parseISO } from "date-fns";
import {
  Loader2, Route, Zap, BatteryCharging, Timer, Calendar,
  Car, ParkingSquare, Zap as ZapIcon, KeyRound, WifiOff,
  MapPin, Clock, TrendingUp,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar,
} from "recharts";
import "leaflet/dist/leaflet.css";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import L from "leaflet";
import { api } from "@/lib/api";
import type { TimelineRange } from "./StatisticsShell";

// Fix Leaflet default icon in Next.js
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

export interface DrivingDashboardProps {
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

interface Geofence {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  radius_meters: number;
}

interface StayEvent {
  label: string;
  latitude: number;
  longitude: number;
  arrivalTime: Date;
  departureTime: Date;
  durationMs: number;
  isCharging: boolean;
  pointCount: number;
}

interface MoveEvent {
  startTime: Date;
  endTime: Date;
  durationMs: number;
}

type ActivityEvent =
  | { type: "stay"; data: StayEvent }
  | { type: "move"; data: MoveEvent };

// ── Helpers ───────────────────────────────────────────────────────────────────

function haversineMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function matchGeofence(lat: number, lon: number, geofences: Geofence[]): Geofence | null {
  for (const gf of geofences) {
    if (haversineMeters(lat, lon, gf.latitude, gf.longitude) <= gf.radius_meters + 50) return gf;
  }
  return null;
}

function buildActivityTimeline(locations: VisitedLocation[], geofences: Geofence[]): ActivityEvent[] {
  if (locations.length === 0) return [];
  const sorted = [...locations].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  const STAY_RADIUS_M = 80;
  const MIN_STAY_MS = 5 * 60 * 1000;
  const events: ActivityEvent[] = [];
  let i = 0;

  while (i < sorted.length) {
    const anchor = sorted[i];
    const anchorTime = new Date(anchor.timestamp);
    let j = i + 1;
    let latSum = anchor.latitude, lonSum = anchor.longitude, count = 1;
    let hasCharging = anchor.source === "charging";

    while (j < sorted.length) {
      const pt = sorted[j];
      const dist = haversineMeters(pt.latitude, pt.longitude, latSum / count, lonSum / count);
      if (dist > STAY_RADIUS_M) break;
      latSum += pt.latitude; lonSum += pt.longitude; count++;
      if (pt.source === "charging") hasCharging = true;
      j++;
    }

    const clusterLat = latSum / count;
    const clusterLon = lonSum / count;
    const departureTime = new Date(sorted[j - 1]?.timestamp ?? anchor.timestamp);
    const durationMs = departureTime.getTime() - anchorTime.getTime();

    if (count >= 2 && durationMs >= MIN_STAY_MS) {
      const gf = matchGeofence(clusterLat, clusterLon, geofences);
      events.push({
        type: "stay",
        data: {
          label: gf ? gf.name : hasCharging ? "Charging Stop" : "Location",
          latitude: clusterLat,
          longitude: clusterLon,
          arrivalTime: anchorTime,
          departureTime,
          durationMs,
          isCharging: hasCharging,
          pointCount: count,
        },
      });
    }
    i = j;
  }
  return events;
}

function formatDuration(seconds: number): string {
  if (seconds <= 0 || !Number.isFinite(seconds)) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${Math.round(seconds)}s`;
}

function formatDurationMs(ms: number): string {
  return formatDuration(ms / 1000);
}

function formatTime(date: Date): string {
  const h = date.getHours();
  const m = date.getMinutes().toString().padStart(2, "0");
  const ampm = h >= 12 ? "PM" : "AM";
  const hour = h % 12 || 12;
  return `${hour}:${m} ${ampm}`;
}

function formatDateTime(date: Date): string {
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${formatTime(date)}`;
}

function StayIcon({ label, isCharging }: { label: string; isCharging: boolean }) {
  if (isCharging) return <Zap size={15} className="text-iv-green" />;
  const l = label.toLowerCase();
  if (l.includes("home")) return <ParkingSquare size={15} className="text-iv-cyan" />;
  if (l.includes("work") || l.includes("office")) return <MapPin size={15} className="text-iv-cyan" />;
  return <MapPin size={15} className="text-iv-muted" />;
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

export function DrivingDashboard({ vehicleId, dateRange }: DrivingDashboardProps) {
  // ── State ──────────────────────────────────────────────────────────────────
  const [trips, setTrips] = useState<TripAnalyticsItem[]>([]);
  const [stats, setStats] = useState<StatisticsRow[]>([]);
  const [odometer, setOdometer] = useState<OdometerItem[]>([]);
  const [timeBudget, setTimeBudget] = useState<TimeBudget | null>(null);
  const [visitedLocations, setVisitedLocations] = useState<VisitedLocation[]>([]);
  const [geofences, setGeofences] = useState<Geofence[]>([]);
  const [loading, setLoading] = useState(true);

  // ── Data fetching ────────────────────────────────────────────────────────────
  // odometer + visited locations fetched WITHOUT date filter (full history for trends)
  // stats + trips are filtered by dateRange
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
        geofencesData,
      ] = await Promise.allSettled([
        api.getTripsAnalytics(vehicleId, 200, fromISO, toISO),
        api.getStatistics(vehicleId, "day", 30, fromISO, toISO),
        // ── odometer: no date filter ── full history for mileage trend
        api.getOdometer(vehicleId, 5000),
        api.getTimeBudget(vehicleId),
        // ── visited locations: no date filter ── all-time for map
        api.getVisitedLocations(vehicleId, 5000),
        api.getGeofences().catch(() => [] as Geofence[]),
      ]);

      setTrips(tripsData.status === "fulfilled" ? (tripsData.value ?? []) : []);
      setStats(statsData.status === "fulfilled" ? (statsData.value ?? []) : []);
      setOdometer(odometerData.status === "fulfilled" ? (odometerData.value ?? []) : []);
      setTimeBudget(budgetData.status === "fulfilled" ? budgetData.value : null);
      setVisitedLocations(locationsData.status === "fulfilled" ? (locationsData.value ?? []) : []);
      setGeofences(geofencesData.status === "fulfilled" ? (geofencesData.value ?? []) : []);
    } catch {
      // swallow
    } finally {
      setLoading(false);
    }
  }, [vehicleId, fromISO, toISO]);

  useEffect(() => {
    fetchData();
    const isLive = !toISO || new Date(toISO) >= new Date();
    if (!isLive) return;
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData, toISO]);

  // ── Timeline (from MovementDashboard) ───────────────────────────────────────
  const timeline = useMemo(() => buildActivityTimeline(visitedLocations, geofences), [visitedLocations, geofences]);
  const stayEvents = useMemo(() => timeline.filter((e) => e.type === "stay").map((e) => e.data as StayEvent), [timeline]);

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

  // Mileage trend chart data (all odometer readings, reversed → chronological)
  const mileageChartData = useMemo(() => {
    return [...odometer]
      .reverse()
      .slice(0, 60)
      .map((o) => ({
        date: format(parseISO(o.captured_at), "d MMM"),
        km: o.mileage_in_km,
      }));
  }, [odometer]);

  // Time budget
  const tb = timeBudget;
  const totalS = tb
    ? Math.max(tb.parked_seconds + tb.driving_seconds + tb.charging_seconds + tb.ignition_seconds + tb.offline_seconds, 1)
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

  // Map center (all-time first visited location)
  const defaultCenter: [number, number] = [54.7, 25.3]; // Lithuania fallback
  const mapCenter = visitedLocations.length > 0
    ? [visitedLocations[visitedLocations.length - 1].latitude, visitedLocations[visitedLocations.length - 1].longitude] as [number, number]
    : defaultCenter;

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

      {/* ── Mileage Trend (all-time odometer, no date filter) ── */}
      {mileageChartData.length > 1 && (
        <div className="glass rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-iv-text">Mileage Trend</h3>
            <span className="text-xs bg-iv-surface border border-iv-border text-iv-muted px-2 py-0.5 rounded-full">All readings</span>
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

      {/* ── Visited Locations Map (all-time, geofences marked) ── */}
      {visitedLocations.length > 0 && (
        <div className="glass rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-semibold text-iv-text">Visited Locations</h3>
          <MapContainer
            center={mapCenter}
            zoom={10}
            className="h-80 rounded-xl z-0"
            style={{ background: "var(--iv-bg)" }}
          >
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            />
            {visitedLocations.map((loc, i) => (
              <CircleMarker
                key={i}
                center={[loc.latitude, loc.longitude]}
                radius={4}
                pathOptions={{ color: "var(--iv-cyan)", fillColor: "var(--iv-cyan)", fillOpacity: 0.6, weight: 1 }}
              >
                <Popup>
                  <div className="text-xs">
                    <p className="font-medium">{formatDateTime(new Date(loc.timestamp))}</p>
                    <p className="text-gray-500">{loc.latitude.toFixed(4)}, {loc.longitude.toFixed(4)}</p>
                    <p className="text-gray-400 capitalize">{loc.source}</p>
                  </div>
                </Popup>
              </CircleMarker>
            ))}
            {geofences.map((gf) => (
              <CircleMarker
                key={gf.id}
                center={[gf.latitude, gf.longitude]}
                radius={gf.radius_meters > 0 ? Math.max(8, gf.radius_meters / 20) : 8}
                pathOptions={{ color: "var(--iv-purple)", fillColor: "var(--iv-purple)", fillOpacity: 0.08, weight: 2, dashArray: "4 4" }}
              >
                <Popup><span className="text-xs font-medium">{gf.name}</span></Popup>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>
      )}

      {/* ── Activity Timeline ── */}
      {stayEvents.length > 0 && (
        <div className="glass rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-semibold text-iv-text">Activity Timeline</h3>
          <div className="relative space-y-1">
            {stayEvents.map((stay, i) => (
              <div key={i} className="flex items-start gap-3 py-2">
                <div className="relative flex flex-col items-center">
                  <div className="w-8 h-8 rounded-full bg-iv-cyan/10 border border-iv-cyan/30 flex items-center justify-center">
                    <StayIcon label={stay.label} isCharging={stay.isCharging} />
                  </div>
                  {i < stayEvents.length - 1 && <div className="w-px h-6 bg-iv-border/50 mt-1" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-iv-text">{stay.label}</p>
                    <span className="text-xs text-iv-muted">{formatDurationMs(stay.durationMs)}</span>
                  </div>
                  <p className="text-xs text-iv-muted">
                    {formatDateTime(stay.arrivalTime)} → {formatDateTime(stay.departureTime)}
                  </p>
                </div>
              </div>
            ))}
          </div>
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
            <div className="space-y-1.5 max-h-72 overflow-y-auto">
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