
"use client";

import { useEffect, useState, useCallback } from "react";
import { format, parseISO } from "date-fns";
import { Loader2, Car, Route, Clock, TrendingUp, Map as MapIcon } from "lucide-react";
import { api } from "@/lib/api";
import type { TimelineRange } from "./StatisticsShell";
import { MapContainer, TileLayer, Polyline, useMap } from 'react-leaflet';
import "leaflet/dist/leaflet.css";

// --- Types ---
export interface TripsDashboardProps {
  vehicleId: string;
  dateRange: TimelineRange;
}

interface TripAnalyticsItem {
  trip_id: number;
  start_time: string;
  end_time: string;
  start_latitude: number;
  start_longitude: number;
  destination_latitude: number;
  destination_longitude: number;
  distance_km: number;
  duration_minutes: number;
  average_speed_kmh: number;
  kwh_used: number | null;
  efficiency_kwh_100km: number | null;
}

// --- Helper Hooks & Functions ---
const useReverseGeocoding = (trips: TripAnalyticsItem[]) => {
  const [locations, setLocations] = useState<Map<string, string>>(new Map());

  const fetchLocationName = useCallback(async (lat: number, lon: number) => {
    try {
      const response = await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}`);
      const data = await response.json();
      return data.display_name || "Unknown Location";
    } catch (error) {
      return "Location";
    }
  }, []);

  useEffect(() => {
    const uniqueCoords = new Map<string, { lat: number; lon: number }>();
    trips.forEach((trip) => {
      if (trip.start_latitude === null || trip.start_longitude === null || 
          trip.destination_latitude === null || trip.destination_longitude === null) {
        return;
      }
      const startKey = `${trip.start_latitude.toFixed(5)},${trip.start_longitude.toFixed(5)}`;
      const endKey = `${trip.destination_latitude.toFixed(5)},${trip.destination_longitude.toFixed(5)}`;
      if (!uniqueCoords.has(startKey)) uniqueCoords.set(startKey, { lat: trip.start_latitude, lon: trip.start_longitude });
      if (!uniqueCoords.has(endKey)) uniqueCoords.set(endKey, { lat: trip.destination_latitude, lon: trip.destination_longitude });
    });

    const fetchAllLocations = async () => {
      const newLocations = new Map<string, string>();
      for (const [key, { lat, lon }] of uniqueCoords.entries()) {
        const name = await fetchLocationName(lat, lon);
        newLocations.set(key, name.split(",")[0] || name);
      }
      setLocations(newLocations);
    };

    if (trips.length > 0) {
      fetchAllLocations();
    }
  }, [trips, fetchLocationName]);

  const getLocationName = (lat: number | null, lon: number | null) => {
    if (lat === null || lon === null) return "Location";
    const key = `${lat.toFixed(5)},${lon.toFixed(5)}`;
    return locations.get(key) || "Location";
  };

  return { getLocationName };
};

function formatDuration(minutes: number): string {
  if (minutes <= 0) return "—";
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function MapController({ activeTripId, trips }: { activeTripId: number | null, trips: TripAnalyticsItem[] }) {
    const map = useMap();
    useEffect(() => {
        const activeTrip = trips.find(t => t.trip_id === activeTripId);
        if (activeTrip) {
            map.flyTo([activeTrip.start_latitude, activeTrip.start_longitude], 13);
        } else if (trips.length > 0) {
            // On initial load, fit all trips in bounds
            const bounds = trips.reduce((acc, trip) => {
                return acc.extend([trip.start_latitude, trip.start_longitude]).extend([trip.destination_latitude, trip.destination_longitude]);
            }, new (L as any).LatLngBounds());
            if (bounds.isValid()) {
                map.fitBounds(bounds, { padding: [50, 50] });
            }
        }
    }, [activeTripId, trips, map]);
    return null;
}


// --- Main Component ---
export function TripsDashboard({ vehicleId, dateRange }: TripsDashboardProps) {
  const [trips, setTrips] = useState<TripAnalyticsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTripId, setActiveTripId] = useState<number | null>(null);

  const { getLocationName } = useReverseGeocoding(trips);

  const fromISO = dateRange.from.toISOString();
  const toISO = dateRange.to.toISOString();

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const list = await api.getTripsAnalytics(vehicleId, 200, fromISO, toISO);
        setTrips(list ?? []);
      } catch {
        setTrips([]);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [vehicleId, fromISO, toISO]);

  const summary = {
    totalTrips: trips.length,
    totalDistance: trips.reduce((acc, trip) => acc + trip.distance_km, 0),
    totalTime: trips.reduce((acc, trip) => acc + trip.duration_minutes, 0),
    avgEfficiency: trips.filter(t => t.efficiency_kwh_100km).reduce((acc, trip, _, arr) => acc + (trip.efficiency_kwh_100km || 0) / arr.length, 0)
  };

  if (loading) {
    return <div className="flex items-center justify-center py-24"><Loader2 className="h-8 w-8 animate-spin text-iv-muted" /></div>;
  }

  if (trips.length === 0) {
    return <div className="py-24 text-center text-sm text-iv-muted">No trips recorded for the selected period.</div>;
  }

  return (
    <div className="space-y-6">
      {/* --- Summary Cards --- */}
      <div className="glass rounded-2xl p-6 space-y-4">
        <h3 className="text-sm font-semibold text-iv-text">Trip Summary</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-iv-surface/60 rounded-xl p-4 border border-iv-border/50 space-y-2">
            <div className="flex items-center gap-2"><Route size={16} className="text-iv-muted" /><span className="text-xs font-semibold text-iv-muted uppercase tracking-wide">Total Trips</span></div>
            <p className="text-2xl font-bold text-iv-text">{summary.totalTrips}</p>
          </div>
          <div className="bg-iv-surface/60 rounded-xl p-4 border border-iv-border/50 space-y-2">
            <div className="flex items-center gap-2"><MapIcon size={16} className="text-iv-muted" /><span className="text-xs font-semibold text-iv-muted uppercase tracking-wide">Total Distance</span></div>
            <p className="text-2xl font-bold text-iv-text">{summary.totalDistance.toFixed(1)} km</p>
          </div>
          <div className="bg-iv-surface/60 rounded-xl p-4 border border-iv-border/50 space-y-2">
            <div className="flex items-center gap-2"><Clock size={16} className="text-iv-muted" /><span className="text-xs font-semibold text-iv-muted uppercase tracking-wide">Total Time</span></div>
            <p className="text-2xl font-bold text-iv-text">{formatDuration(summary.totalTime)}</p>
          </div>
          <div className="bg-iv-surface/60 rounded-xl p-4 border border-iv-cyan/30 space-y-2">
            <div className="flex items-center gap-2"><TrendingUp size={16} className="text-iv-cyan" /><span className="text-xs font-semibold text-iv-muted uppercase tracking-wide">Avg. Efficiency</span></div>
            <p className="text-2xl font-bold text-iv-cyan">{summary.avgEfficiency > 0 ? summary.avgEfficiency.toFixed(2) : '—'}</p>
            <p className="text-xs text-iv-muted">kWh/100km</p>
          </div>
        </div>
      </div>

      {/* --- Main Content --- */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 glass rounded-2xl overflow-hidden h-96 lg:h-auto">
          <MapContainer center={[54.6872, 25.2797]} zoom={6} className="h-full w-full" scrollWheelZoom={false}>
            <TileLayer
              attribution='&copy; <a href="https://carto.com/attributions">CARTO</a>'
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            />
            {trips.filter(t => t.start_latitude !== null && t.start_longitude !== null && t.destination_latitude !== null && t.destination_longitude !== null).map(trip => {
              const isActive = trip.trip_id === activeTripId;
              return (
                <Polyline
                  key={trip.trip_id}
                  positions={[[trip.start_latitude!, trip.start_longitude!], [trip.destination_latitude!, trip.destination_longitude!]]}
                  pathOptions={{
                    color: isActive ? "#00D4FF" : "#475569",
                    weight: isActive ? 4 : 2,
                    opacity: isActive ? 1.0 : 0.6
                  }}
                />
              )
            })}
            <MapController activeTripId={activeTripId} trips={trips} />
          </MapContainer>
        </div>
        <div className="glass rounded-2xl p-6 space-y-3">
          <h3 className="text-sm font-semibold text-iv-text">Trips</h3>
          <div className="space-y-2 max-h-[30rem] overflow-y-auto no-scrollbar pr-1">
            {trips.map((trip) => (
              <div
                key={trip.trip_id}
                className={`flex items-center gap-3 p-3 rounded-xl bg-iv-surface/60 border transition-colors cursor-pointer ${activeTripId === trip.trip_id ? 'border-iv-cyan/50' : 'border-iv-border/50 hover:border-iv-border'}`}
                onClick={() => setActiveTripId(trip.trip_id)}
              >
                <div className="p-2 rounded-full shrink-0 bg-iv-cyan/10">
                  <Car size={14} className="text-iv-cyan" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-iv-text truncate" title={`${getLocationName(trip.start_latitude, trip.start_longitude)} to ${getLocationName(trip.destination_latitude, trip.destination_longitude)}`}>
                    {getLocationName(trip.start_latitude, trip.start_longitude)} <span className="text-iv-muted">→</span> {getLocationName(trip.destination_latitude, trip.destination_longitude)}
                  </p>
                  <p className="text-xs text-iv-muted">{format(parseISO(trip.start_time), "MMM d, yyyy HH:mm")}</p>
                </div>
                <div className="text-right shrink-0">
                    <p className="text-sm font-bold text-iv-text">{trip.distance_km.toFixed(1)} km</p>
                    <p className="text-xs text-iv-cyan">{trip.efficiency_kwh_100km ? `${trip.efficiency_kwh_100km.toFixed(2)} kWh/100` : ''}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
