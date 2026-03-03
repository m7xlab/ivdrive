"use client";

import { useEffect, useState, useCallback } from "react";
import { format, parseISO } from "date-fns";
import { MapPin, Loader2, Route } from "lucide-react";
import { api } from "@/lib/api";
import type { TimelineRange } from "./StatisticsShell";

export interface TripsDashboardProps {
  vehicleId: string;
  dateRange: TimelineRange;
}

interface TripRow {
  id: number;
  start_date: string;
  end_date: string | null;
  start_lat: number | null;
  start_lon: number | null;
  end_lat: number | null;
  end_lon: number | null;
  start_odometer: number | null;
  end_odometer: number | null;
}

function formatDuration(start: string, end: string | null): string {
  if (!end) return "—";
  try {
    const a = parseISO(start.replace("Z", "+00:00"));
    const b = parseISO(end.replace("Z", "+00:00"));
    const sec = (b.getTime() - a.getTime()) / 1000;
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m`;
    return `${Math.round(sec)}s`;
  } catch {
    return "—";
  }
}

function formatLocation(lat: number | null, lon: number | null): string {
  if (lat == null || lon == null) return "—";
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

function distanceKm(t: TripRow): number {
  if (t.end_odometer != null && t.start_odometer != null) return t.end_odometer - t.start_odometer;
  return 0;
}

export function TripsDashboard({ vehicleId, dateRange }: TripsDashboardProps) {
  const [trips, setTrips] = useState<TripRow[]>([]);
  const [loading, setLoading] = useState(true);

  const fromISO = dateRange.from.toISOString();
  const toISO = dateRange.to.toISOString();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.getTrips(vehicleId, 200, fromISO, toISO);
      setTrips(list ?? []);
    } catch {
      setTrips([]);
    } finally {
      setLoading(false);
    }
  }, [vehicleId, fromISO, toISO]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const top10Longest = [...trips]
    .filter((t) => t.end_odometer != null && t.start_odometer != null)
    .sort((a, b) => distanceKm(b) - distanceKm(a))
    .slice(0, 10);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-iv-muted" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-iv-muted">
        List of all trips recorded. Start and destination are shown as coordinates when no location names are
        available.
      </p>

      <div className="overflow-hidden rounded-lg border border-iv-border bg-iv-surface">
        <div className="flex items-center gap-2 border-b border-iv-border px-4 py-3">
          <MapPin className="h-5 w-5 text-iv-muted" />
          <h3 className="font-medium">Trips</h3>
        </div>
        {trips.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-iv-muted">No trips in the selected period.</div>
        ) : (
          <>
            {/* Mobile card view */}
            <div className="block sm:hidden divide-y divide-iv-border/50">
              {trips.map((t) => (
                <div key={t.id} className="px-4 py-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs text-iv-muted">
                      {format(parseISO(t.start_date.replace("Z", "+00:00")), "yyyy-MM-dd HH:mm")}
                    </span>
                    <span className="text-sm font-bold text-iv-cyan shrink-0">{distanceKm(t).toFixed(1)} km</span>
                  </div>
                  <div className="grid grid-cols-[5.5rem_1fr] gap-y-1 text-xs">
                    <span className="text-iv-muted">Duration</span>
                    <span className="text-iv-text">{formatDuration(t.start_date, t.end_date)}</span>
                    <span className="text-iv-muted">Odometer</span>
                    <span className="text-iv-text">{t.end_odometer != null ? t.end_odometer.toLocaleString() : "—"}</span>
                    <span className="text-iv-muted">From</span>
                    <span className="font-mono text-[10px] text-iv-text truncate">{formatLocation(t.start_lat, t.start_lon)}</span>
                    <span className="text-iv-muted">To</span>
                    <span className="font-mono text-[10px] text-iv-text truncate">{formatLocation(t.end_lat, t.end_lon)}</span>
                  </div>
                </div>
              ))}
            </div>
            {/* Desktop table view */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-iv-border text-left text-iv-muted">
                    <th className="px-4 py-2 font-medium">Start Date</th>
                    <th className="px-4 py-2 font-medium">Start</th>
                    <th className="px-4 py-2 font-medium">Destination</th>
                    <th className="px-4 py-2 font-medium">Duration</th>
                    <th className="px-4 py-2 font-medium">Length (km)</th>
                    <th className="px-4 py-2 font-medium">Odometer</th>
                  </tr>
                </thead>
                <tbody>
                  {trips.map((t) => (
                    <tr key={t.id} className="border-b border-iv-border/50 last:border-0">
                      <td className="px-4 py-2">
                        {format(parseISO(t.start_date.replace("Z", "+00:00")), "yyyy-MM-dd HH:mm")}
                      </td>
                      <td className="max-w-[180px] truncate px-4 py-2 text-iv-muted">
                        {formatLocation(t.start_lat, t.start_lon)}
                      </td>
                      <td className="max-w-[180px] truncate px-4 py-2 text-iv-muted">
                        {formatLocation(t.end_lat, t.end_lon)}
                      </td>
                      <td className="px-4 py-2">{formatDuration(t.start_date, t.end_date)}</td>
                      <td className="px-4 py-2">{distanceKm(t).toFixed(1)}</td>
                      <td className="px-4 py-2">{t.end_odometer != null ? t.end_odometer.toLocaleString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      {top10Longest.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-iv-border bg-iv-surface">
          <div className="flex items-center gap-2 border-b border-iv-border px-4 py-3">
            <Route className="h-5 w-5 text-iv-muted" />
            <h3 className="font-medium">Top 10 longest trips</h3>
          </div>
          <>
            {/* Mobile card view */}
            <div className="block sm:hidden divide-y divide-iv-border/50">
              {top10Longest.map((t) => (
                <div key={t.id} className="px-4 py-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs text-iv-muted truncate">
                      {format(parseISO(t.start_date.replace("Z", "+00:00")), "yyyy-MM-dd HH:mm")}
                    </p>
                    <p className="font-mono text-[10px] text-iv-muted truncate">{formatLocation(t.end_lat, t.end_lon)}</p>
                  </div>
                  <span className="text-sm font-bold text-iv-cyan shrink-0">{distanceKm(t).toFixed(1)} km</span>
                </div>
              ))}
            </div>
            {/* Desktop table view */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="w-full min-w-[320px] text-sm">
                <thead>
                  <tr className="border-b border-iv-border text-left text-iv-muted">
                    <th className="px-4 py-2 font-medium">Start Date</th>
                    <th className="px-4 py-2 font-medium">Length (km)</th>
                    <th className="px-4 py-2 font-medium">Destination (coords)</th>
                  </tr>
                </thead>
                <tbody>
                  {top10Longest.map((t) => (
                    <tr key={t.id} className="border-b border-iv-border/50 last:border-0">
                      <td className="px-4 py-2">
                        {format(parseISO(t.start_date.replace("Z", "+00:00")), "yyyy-MM-dd HH:mm")}
                      </td>
                      <td className="px-4 py-2">{distanceKm(t).toFixed(1)}</td>
                      <td className="max-w-[180px] truncate px-4 py-2 text-iv-muted">
                        {formatLocation(t.end_lat, t.end_lon)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        </div>
      )}
    </div>
  );
}
