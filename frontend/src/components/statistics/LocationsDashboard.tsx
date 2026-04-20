"use client";

import { useEffect, useState, useCallback } from "react";
import { format, parseISO } from "date-fns";
import { MapPin, Loader2, Info } from "lucide-react";
import { api } from "@/lib/api";
import type { TimelineRange } from "./StatisticsShell";

export interface LocationsDashboardProps {
  vehicleId: string;
  dateRange: TimelineRange;
}

interface PositionRow {
  latitude: number;
  longitude: number;
  captured_at: string;
}

/** Round to 4 decimals (~11 m) to cluster nearby points as one "place". */
function placeKey(lat: number, lon: number): string {
  return `${lat.toFixed(4)},${lon.toFixed(4)}`;
}

export function LocationsDashboard({ vehicleId, dateRange }: LocationsDashboardProps) {
  const [positions, setPositions] = useState<PositionRow[]>([]);
  const [loading, setLoading] = useState(true);

  const fromISO = dateRange.from.toISOString();
  const toISO = dateRange.to.toISOString();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.getPositions(vehicleId, 1000, fromISO, toISO);
      setPositions(list ?? []);
    } catch {
      setPositions([]);
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

  const distinctPlaces = new Set(positions.map((p) => placeKey(p.latitude, p.longitude))).size;
  const lastPositions = [...positions]
    .sort((a, b) => new Date(b.captured_at).getTime() - new Date(a.captured_at).getTime())
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
        Position-based overview. Full location statistics (cities, states, countries, neighbourhoods) require a
        locations entity or reverse geocoding—not yet available in iVDrive.
      </p>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-iv-surface p-4">
          <div className="rounded-lg bg-iv-blue/15 p-3">
            <MapPin className="h-6 w-6 text-iv-blue" />
          </div>
          <div>
            <p className="text-xs font-medium text-iv-muted">Position records</p>
            <p className="text-2xl font-bold text-iv-text">{positions.length}</p>
            <p className="text-xs text-iv-muted">in selected period</p>
          </div>
        </div>
        <div className="flex items-center gap-4 rounded-lg border border-iv-border bg-iv-surface p-4">
          <div className="rounded-lg bg-iv-blue/15 p-3">
            <MapPin className="h-6 w-6 text-iv-blue" />
          </div>
          <div>
            <p className="text-xs font-medium text-iv-muted">Distinct places</p>
            <p className="text-2xl font-bold text-iv-text">{distinctPlaces}</p>
            <p className="text-xs text-iv-muted">approx. (~11 m resolution)</p>
          </div>
        </div>
      </div>

      <div className="flex gap-3 rounded-lg border border-iv-blue/30 bg-iv-blue/5 p-4">
        <Info className="h-5 w-5 shrink-0 text-iv-blue" />
        <p className="text-sm text-iv-muted">
          Total locations, cities, states, and countries as in the original dashboard require a backend locations
          table (or derivation from positions/trips with reverse geocoding). Until then, only position-based counts
          are shown above.
        </p>
      </div>

      <div className="overflow-hidden rounded-lg border border-iv-border bg-iv-surface">
        <div className="flex items-center gap-2 border-b border-iv-border px-4 py-3">
          <MapPin className="h-5 w-5 text-iv-muted" />
          <h3 className="font-medium">Last visited (by position)</h3>
        </div>
        {lastPositions.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-iv-muted">No positions in the selected period.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[320px] text-sm">
              <thead>
                <tr className="border-b border-iv-border text-left text-iv-muted">
                  <th className="px-4 py-2 font-medium">Date</th>
                  <th className="px-4 py-2 font-medium">Coordinates</th>
                </tr>
              </thead>
              <tbody>
                {lastPositions.map((p, i) => (
                  <tr key={`${p.captured_at}-${i}`} className="border-b border-iv-border/50 last:border-0">
                    <td className="px-4 py-2">
                      {format(parseISO(p.captured_at.replace("Z", "+00:00")), "yyyy-MM-dd HH:mm")}
                    </td>
                    <td className="font-mono text-sm text-iv-muted px-4 py-2">
                      {p.latitude.toFixed(5)}, {p.longitude.toFixed(5)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
