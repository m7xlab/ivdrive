"use client";

import { useEffect, useState, useCallback } from "react";
import { MapPin, Loader2, Zap, Car, Clock, Home, Briefcase, ParkingSquare, WifiOff, KeyRound } from "lucide-react";
import "leaflet/dist/leaflet.css";
import { api } from "@/lib/api";
import { formatSmartDuration } from "@/lib/format";
import type { TimelineRange } from "./StatisticsShell";

export interface MovementDashboardProps {
  vehicleId: string;
  dateRange: TimelineRange;
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

interface TimeBudget {
  parked_seconds: number;
  driving_seconds: number;
  charging_seconds: number;
  ignition_seconds: number;
  offline_seconds: number;
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
    } else {
      const last = events[events.length - 1];
      if (last?.type === "move") {
        (last.data as MoveEvent).endTime = new Date(anchor.timestamp);
        (last.data as MoveEvent).durationMs = (last.data as MoveEvent).endTime.getTime() - (last.data as MoveEvent).startTime.getTime();
      } else {
        events.push({ type: "move", data: { startTime: anchorTime, endTime: anchorTime, durationMs: 0 } });
      }
    }
    i = j;
  }
  return events;
}

function formatDurationMs(ms: number): string {
  return formatSmartDuration(ms / 60000);
}

/** Safe time formatter — avoids SSR/client hydration mismatch from toLocaleTimeString. */
function formatTime(date: Date): string {
  const h = date.getHours();
  const m = date.getMinutes().toString().padStart(2, "0");
  const ampm = h >= 12 ? "PM" : "AM";
  const hour = h % 12 || 12;
  return `${hour}:${m} ${ampm}`;
}

/** Safe datetime formatter for map popups. */
function formatDateTime(date: Date): string {
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${formatTime(date)}`;
}

function StayIcon({ label, isCharging }: { label: string; isCharging: boolean }) {
  if (isCharging) return <Zap size={15} className="text-iv-green" />;
  const l = label.toLowerCase();
  if (l.includes("home")) return <Home size={15} className="text-iv-cyan" />;
  if (l.includes("work")) return <Briefcase size={15} className="text-iv-cyan" />;
  return <MapPin size={15} className="text-iv-muted" />;
}

export function MovementDashboard({ vehicleId, dateRange }: MovementDashboardProps) {
  const [locations, setLocations] = useState<VisitedLocation[]>([]);
  const [geofences, setGeofences] = useState<Geofence[]>([]);
  const [timeBudget, setTimeBudget] = useState<TimeBudget | null>(null);
  const [loadingBudget, setLoadingBudget] = useState(true);
  const [loadingPeriod, setLoadingPeriod] = useState(true);

  const fromISO = dateRange.from.toISOString();
  const toISO = dateRange.to.toISOString();

  // All-time time budget — fetched once, not date-dependent
  useEffect(() => {
    setLoadingBudget(true);
    api.getTimeBudget(vehicleId)
      .then(setTimeBudget)
      .finally(() => setLoadingBudget(false));
  }, [vehicleId]);

  // Period-based location data — refetches when date range changes
  const fetchPeriodData = useCallback(async () => {
    setLoadingPeriod(true);
    try {
      const [locs, gfs] = await Promise.all([
        api.getVisitedLocations(vehicleId, 5000, fromISO, toISO),
        api.getGeofences().catch(() => []),
      ]);
      setLocations(locs ?? []);
      setGeofences(gfs ?? []);
    } catch {
      setLocations([]);
    } finally {
      setLoadingPeriod(false);
    }
  }, [vehicleId, fromISO, toISO]);

  useEffect(() => { fetchPeriodData(); }, [fetchPeriodData]);

  const timeline = buildActivityTimeline(locations, geofences);
  const stayEvents = timeline.filter((e) => e.type === "stay").map((e) => e.data as StayEvent);

  // Top places by time spent
  const placeMap = new Map<string, { label: string; lat: number; lon: number; ms: number; charging: boolean }>();
  for (const s of stayEvents) {
    const key = `${s.latitude.toFixed(3)},${s.longitude.toFixed(3)}`;
    const existing = placeMap.get(key);
    if (existing) existing.ms += s.durationMs;
    else placeMap.set(key, { label: s.label, lat: s.latitude, lon: s.longitude, ms: s.durationMs, charging: s.isCharging });
  }
  const topPlaces = [...placeMap.values()].sort((a, b) => b.ms - a.ms).slice(0, 5);

  const tb = timeBudget;
  const totalS = Math.max(
    (tb?.parked_seconds ?? 0) + (tb?.driving_seconds ?? 0) + (tb?.charging_seconds ?? 0) +
    (tb?.ignition_seconds ?? 0) + (tb?.offline_seconds ?? 0), 1
  );
  const allBuckets = tb ? [
    { label: "Parked",   seconds: tb.parked_seconds,   barColor: "bg-iv-text-muted/50", textColor: "text-iv-text",     accent: "border-iv-border",      icon: <ParkingSquare size={16} className="text-iv-muted" /> },
    { label: "Driving",  seconds: tb.driving_seconds,  barColor: "bg-iv-cyan",          textColor: "text-iv-cyan",     accent: "border-iv-cyan/30",     icon: <Car size={16} className="text-iv-cyan" /> },
    { label: "Charging", seconds: tb.charging_seconds, barColor: "bg-iv-green",         textColor: "text-iv-green",    accent: "border-iv-green/30",    icon: <Zap size={16} className="text-iv-green" /> },
    { label: "Ignition", seconds: tb.ignition_seconds, barColor: "bg-yellow-500/70",    textColor: "text-yellow-400",  accent: "border-yellow-500/30",  icon: <KeyRound size={16} className="text-yellow-400" /> },
    { label: "Offline",  seconds: tb.offline_seconds,  barColor: "bg-iv-border",        textColor: "text-iv-muted",    accent: "border-iv-border",      icon: <WifiOff size={16} className="text-iv-muted" /> },
  ] : [];
  const visibleBuckets = allBuckets.filter((b) => b.seconds > 60);

  return (
    <div className="space-y-6">

      {/* ── All-time Time Budget ── */}
      <div className="glass rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-iv-text">Time Budget</h3>
          <span className="text-xs bg-iv-surface border border-iv-border text-iv-muted px-2 py-0.5 rounded-full">All-time</span>
        </div>

        {loadingBudget ? (
          <div className="flex items-center gap-2 text-iv-muted text-sm py-4">
            <Loader2 size={16} className="animate-spin" /> Loading…
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              {allBuckets.map((b) => (
                <div key={b.label} className={`bg-iv-surface/60 rounded-xl p-4 border ${b.accent} space-y-2`}>
                  <div className="flex items-center gap-2">
                    {b.icon}
                    <span className="text-xs font-semibold text-iv-muted uppercase tracking-wide">{b.label}</span>
                  </div>
                  <p className={`text-2xl font-bold ${b.textColor}`}>{formatSmartDuration(b.seconds / 60)}</p>
                  <p className="text-xs text-iv-muted">{((b.seconds / totalS) * 100).toFixed(1)}%</p>
                </div>
              ))}
            </div>

            {visibleBuckets.length > 0 && (
              <div className="space-y-2">
                <div className="flex rounded-full overflow-hidden h-2.5 gap-px bg-iv-border/30">
                  {visibleBuckets.map((b) => (
                    <div key={b.label} className={`${b.barColor} transition-all`}
                      style={{ width: `${(b.seconds / totalS) * 100}%` }}
                      title={`${b.label}: ${formatSmartDuration(b.seconds / 60)}`} />
                  ))}
                </div>
                <div className="flex gap-4 flex-wrap">
                  {visibleBuckets.map((b) => (
                    <span key={b.label} className="flex items-center gap-1.5 text-xs text-iv-muted">
                      <span className={`inline-block w-2 h-2 rounded-full ${b.barColor}`} />
                      {b.label} · {formatSmartDuration(b.seconds / 60)}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Period badge for lower sections */}
      <div className="flex items-center gap-2">
        <div className="h-px flex-1 bg-iv-border/40" />
        <span className="text-xs bg-iv-surface border border-iv-border text-iv-muted px-2 py-0.5 rounded-full flex items-center gap-1">
          <Clock size={10} /> Selected period
        </span>
        <div className="h-px flex-1 bg-iv-border/40" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Top Places */}
        <div className="glass rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-iv-text">Top Places</h3>
          {topPlaces.length === 0 ? (
            <p className="text-sm text-iv-muted py-6 text-center">No distinct places detected</p>
          ) : (
            <div className="space-y-2">
              {topPlaces.map((place) => (
                <div key={`${place.lat.toFixed(5)},${place.lon.toFixed(5)}`} className="flex items-center gap-3 p-3 rounded-xl bg-iv-surface/60 border border-iv-border/50">
                  <div className={`p-2 rounded-full shrink-0 ${place.charging ? "bg-iv-green/10" : "bg-iv-cyan/10"}`}>
                    {place.charging ? <Zap size={14} className="text-iv-green" /> : <MapPin size={14} className="text-iv-cyan" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-iv-text truncate">{place.label}</p>
                    <p className="text-xs text-iv-muted">{place.lat.toFixed(5)}, {place.lon.toFixed(5)}</p>
                  </div>
                  <span className="text-sm font-bold text-iv-text shrink-0">{formatDurationMs(place.ms)}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Activity Timeline */}
        <div className="glass rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-iv-text">Activity Timeline</h3>
          <div className="space-y-0.5 max-h-72 overflow-y-auto no-scrollbar">
            {timeline.length === 0 ? (
              <p className="text-sm text-iv-muted py-6 text-center">No activity detected</p>
            ) : timeline.map((event) => {
              if (event.type === "stay") {
                const s = event.data as StayEvent;
                return (
                  <div key={`stay-${s.arrivalTime.getTime()}`} className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-iv-surface/60 transition-colors">
                    <div className={`mt-0.5 p-1.5 rounded-full shrink-0 ${s.isCharging ? "bg-iv-green/10" : "bg-iv-surface"}`}>
                      <StayIcon label={s.label} isCharging={s.isCharging} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-iv-text">{s.label}</p>
                      <p className="text-xs text-iv-muted">
                        {formatTime(s.arrivalTime)} → {formatTime(s.departureTime)}
                      </p>
                    </div>
                    <span className="text-xs font-bold text-iv-text shrink-0">{formatDurationMs(s.durationMs)}</span>
                  </div>
                );
              } else {
                return (
                  <div key={`move-${(event.data as MoveEvent).startTime.getTime()}`} className="flex items-center gap-3 px-2.5 py-1.5 text-iv-muted">
                    <div className="p-1.5 rounded-full bg-iv-surface/40 shrink-0"><Car size={13} className="text-iv-cyan" /></div>
                    <p className="text-xs flex-1 text-iv-cyan">Driving</p>
                  </div>
                );
              }
            })}
          </div>
        </div>
      </div>

      {/* Map */}
      <MovementMap locations={locations} stayEvents={stayEvents} />
    </div>
  );
}

function MovementMap({ locations, stayEvents }: { locations: VisitedLocation[]; stayEvents: StayEvent[] }) {
  const [MapComponents, setMapComponents] = useState<any>(null);
  const [mounted, setMounted] = useState(false);
  const [isDark, setIsDark] = useState(true);

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    if (!mounted) return;
    // Detect current theme
    const dark = document.documentElement.classList.contains("dark") ||
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    setIsDark(dark);

    // Watch for theme changes
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains("dark"));
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

    import("react-leaflet").then((L) => {
      setMapComponents({ MapContainer: L.MapContainer, TileLayer: L.TileLayer, CircleMarker: L.CircleMarker, Popup: L.Popup, ZoomControl: L.ZoomControl });
    });

    return () => observer.disconnect();
  }, [mounted]);

  if (!MapComponents || locations.length === 0) {
    return (
      <div className="glass rounded-xl h-64 flex items-center justify-center text-iv-muted text-sm">
        {!MapComponents ? "Loading map…" : "No location data"}
      </div>
    );
  }

  const { MapContainer, TileLayer, CircleMarker, Popup, ZoomControl } = MapComponents;
  const latSum = locations.reduce((a, p) => a + p.latitude, 0);
  const lonSum = locations.reduce((a, p) => a + p.longitude, 0);
  const center: [number, number] = [latSum / locations.length, lonSum / locations.length];
  const maxMs = Math.max(...stayEvents.map((s) => s.durationMs), 1);

  // Tile URLs matching app theme
  const tileUrl = isDark
    ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
    : "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";

  return (
    <div className="glass rounded-xl overflow-hidden">
      <div className="p-3 border-b border-iv-border text-xs text-iv-muted flex gap-4">
        <span className="flex items-center gap-1.5"><span className="inline-block w-2.5 h-2.5 rounded-full bg-blue-400/70" /> Position trail</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-2.5 h-2.5 rounded-full bg-[#4BA82E]" /> Stay cluster</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-2.5 h-2.5 rounded-full bg-[#00D4FF]" /> Charging</span>
      </div>
      <div className="h-[420px]">
        <MapContainer center={center} zoom={11} scrollWheelZoom zoomControl={false}
          style={{ width: "100%", height: "100%" }}>
          <TileLayer url={tileUrl} attribution='&copy; <a href="https://carto.com/attributions">CARTO</a>' />
          <ZoomControl position="bottomleft" />

          {/* Position trail */}
          {locations.map((loc) => (
            <CircleMarker key={`p-${loc.timestamp}`}
              center={[loc.latitude, loc.longitude]}
              radius={2.5}
              pathOptions={{ color: "#60a5fa", fillColor: "#60a5fa", fillOpacity: 0.45, weight: 0 }} />
          ))}

          {/* Stay clusters — radius proportional to time */}
          {stayEvents.map((s) => {
            const radius = 12 + (s.durationMs / maxMs) * 28;
            const color = s.isCharging ? "#4BA82E" : "#00D4FF";
            return (
              <CircleMarker key={`s-${s.arrivalTime.getTime()}-${s.latitude.toFixed(4)}`}
                center={[s.latitude, s.longitude]}
                radius={radius}
                pathOptions={{ color, fillColor: color, fillOpacity: 0.2, weight: 2 }}>
                <Popup>
                  <div style={{ fontSize: 12, lineHeight: 1.5 }}>
                    <strong>{s.label}</strong><br />
                    {formatDurationMs(s.durationMs)}<br />
                    <span style={{ color: "#888" }}>{formatDateTime(s.arrivalTime)}</span>
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>
    </div>
  );
}
