
"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { format, parseISO, getYear, getMonth } from "date-fns";
import { Loader2, Car, Route, Clock, TrendingUp, Map as MapIcon, Calendar } from "lucide-react";
import { api } from "@/lib/api";
import { MapContainer, TileLayer, Polyline, useMap } from 'react-leaflet';
import "leaflet/dist/leaflet.css";

// --- Types ---
export interface TripsDashboardProps {
  vehicleId: string;
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

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

// --- Helper Hooks & Functions ---
const useReverseGeocoding = (trips: TripAnalyticsItem[]) => {
  const [locations, setLocations] = useState<Map<string, string>>(new Map());

  const fetchLocationName = useCallback(async (lat: number, lon: number) => {
    try {
      const data = await api.reverseGeocode(lat, lon);
      return data.display_name || "Location";
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
      const newLocations = new Map<string, string>(locations);
      const entries = Array.from(uniqueCoords.entries()).filter(([key]) => !locations.has(key));
      
      if (entries.length === 0) return;

      for (const [key, { lat, lon }] of entries) {
        const name = await fetchLocationName(lat, lon);
        newLocations.set(key, name);
      }
      setLocations(newLocations);
    };

    fetchAllLocations();
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
            const bounds = trips.reduce((acc, trip) => {
                if (trip.start_latitude && trip.start_longitude && trip.destination_latitude && trip.destination_longitude) {
                  acc.extend([trip.start_latitude, trip.start_longitude]).extend([trip.destination_latitude, trip.destination_longitude]);
                }
                return acc;
            }, new (window as any).L.LatLngBounds());
            if (bounds.isValid()) {
                map.fitBounds(bounds, { padding: [50, 50] });
            }
        }
    }, [activeTripId, trips, map]);
    return null;
}


// --- Main Component ---
export function TripsDashboard({ vehicleId }: TripsDashboardProps) {
  const [allTrips, setAllTrips] = useState<TripAnalyticsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTripId, setActiveTripId] = useState<number | null>(null);
  
  // Year/Month selection
  const [selectedYear, setSelectedYear] = useState<number>(getYear(new Date()));
  const [selectedMonth, setSelectedMonth] = useState<number | null>(null);
  const [visibleCount, setVisibleCount] = useState(10);

  const { getLocationName } = useReverseGeocoding(allTrips);

  // Initial load: Fetch all trips for building navigation
  useEffect(() => {
    const fetchInitialData = async () => {
      setLoading(true);
      try {
        const list = await api.getTripsAnalytics(vehicleId, 2000);
        setAllTrips(list ?? []);
        
        if (list && list.length > 0) {
          const latest = list[0];
          const d = parseISO(latest.start_time);
          setSelectedYear(getYear(d));
          setSelectedMonth(getMonth(d));
        }
      } catch {
        setAllTrips([]);
      } finally {
        setLoading(false);
      }
    };
    fetchInitialData();
  }, [vehicleId]);

  // Hierarchical Structure
  const structure = useMemo(() => {
    const years: Record<number, Set<number>> = {};
    allTrips.forEach(t => {
      const d = parseISO(t.start_time);
      const y = getYear(d);
      const m = getMonth(d);
      if (!years[y]) years[y] = new Set();
      years[y].add(m);
    });
    return Object.entries(years)
      .map(([year, months]) => ({
        year: parseInt(year),
        months: Array.from(months).sort((a, b) => b - a)
      }))
      .sort((a, b) => b.year - a.year);
  }, [allTrips]);

  // Filtered trips for the active view
  const currentMonthTrips = useMemo(() => {
    if (selectedMonth === null) return [];
    return allTrips.filter(t => {
      const d = parseISO(t.start_time);
      return getYear(d) === selectedYear && getMonth(d) === selectedMonth;
    });
  }, [allTrips, selectedYear, selectedMonth]);

  const visibleTrips = useMemo(() => {
    return currentMonthTrips.slice(0, visibleCount);
  }, [currentMonthTrips, visibleCount]);

  const summary = useMemo(() => ({
    totalTrips: currentMonthTrips.length,
    totalDistance: currentMonthTrips.reduce((acc, trip) => acc + trip.distance_km, 0),
    totalTime: currentMonthTrips.reduce((acc, trip) => acc + trip.duration_minutes, 0),
    avgEfficiency: currentMonthTrips.filter(t => t.efficiency_kwh_100km).reduce((acc, trip, _, arr) => acc + (trip.efficiency_kwh_100km || 0) / arr.length, 0)
  }), [currentMonthTrips]);

  const handleMonthClick = (year: number, month: number) => {
    setSelectedYear(year);
    setSelectedMonth(month === selectedMonth && year === selectedYear ? null : month);
    setVisibleCount(10);
  };

  if (loading) {
    return <div className="flex items-center justify-center py-24"><Loader2 className="h-8 w-8 animate-spin text-iv-muted" /></div>;
  }

  if (allTrips.length === 0) {
    return <div className="py-24 text-center text-sm text-iv-muted">No trips recorded yet.</div>;
  }

  return (
    <div className="space-y-6">
      {/* --- Hierarchical Navigation --- */}
      <div className="flex flex-wrap gap-2 items-center">
        {structure.map(({ year, months }) => (
          <div key={year} className="flex items-center gap-1 bg-iv-surface/40 rounded-full p-1 border border-iv-border/30">
            <div className="px-3 py-1 text-xs font-bold text-iv-muted uppercase tracking-tighter">{year}</div>
            <div className="flex gap-1">
              {months.map(m => {
                const isActive = selectedYear === year && selectedMonth === m;
                return (
                  <button
                    key={m}
                    onClick={() => handleMonthClick(year, m)}
                    className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${isActive ? 'bg-iv-cyan text-iv-surface' : 'bg-iv-surface/60 text-iv-text hover:bg-iv-border'}`}
                  >
                    {MONTHS[m]}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {selectedMonth !== null && (
        <>
          {/* --- Summary Cards --- */}
          <div className="glass rounded-2xl p-6 space-y-4">
            <h3 className="text-sm font-semibold text-iv-text flex items-center gap-2">
              <Calendar size={14} className="text-iv-cyan" />
              {MONTHS[selectedMonth]} {selectedYear} Summary
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-iv-surface/60 rounded-xl p-4 border border-iv-border/50 space-y-1">
                <span className="text-[10px] font-bold text-iv-muted uppercase">Trips</span>
                <p className="text-xl font-bold text-iv-text">{summary.totalTrips}</p>
              </div>
              <div className="bg-iv-surface/60 rounded-xl p-4 border border-iv-border/50 space-y-1">
                <span className="text-[10px] font-bold text-iv-muted uppercase">Distance</span>
                <p className="text-xl font-bold text-iv-text">{summary.totalDistance.toFixed(1)} km</p>
              </div>
              <div className="bg-iv-surface/60 rounded-xl p-4 border border-iv-border/50 space-y-1">
                <span className="text-[10px] font-bold text-iv-muted uppercase">Duration</span>
                <p className="text-xl font-bold text-iv-text">{formatDuration(summary.totalTime)}</p>
              </div>
              <div className="bg-iv-surface/60 rounded-xl p-4 border border-iv-cyan/30 space-y-1">
                <span className="text-[10px] font-bold text-iv-cyan uppercase tracking-wider">Avg. Eff</span>
                <p className="text-xl font-bold text-iv-cyan">{summary.avgEfficiency > 0 ? summary.avgEfficiency.toFixed(1) : '—'}</p>
              </div>
            </div>
          </div>

          {/* --- Main Content --- */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 glass rounded-2xl overflow-hidden h-96 lg:h-[35rem]">
              <MapContainer center={[54.6872, 25.2797]} zoom={6} className="h-full w-full" scrollWheelZoom={true}>
                <TileLayer
                  attribution='&copy; <a href="https://carto.com/attributions">CARTO</a>'
                  url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                />
                {visibleTrips.filter(t => t.start_latitude && t.destination_latitude).map(trip => {
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
                <MapController activeTripId={activeTripId} trips={visibleTrips} />
              </MapContainer>
            </div>
            
            <div className="glass rounded-2xl p-6 flex flex-col h-[35rem]">
              <h3 className="text-sm font-semibold text-iv-text mb-4">Trips</h3>
              <div className="flex-1 space-y-2 overflow-y-auto no-scrollbar pr-1">
                {visibleTrips.map((trip) => (
                  <div
                    key={trip.trip_id}
                    className={`flex items-center gap-3 p-3 rounded-xl bg-iv-surface/60 border transition-colors cursor-pointer ${activeTripId === trip.trip_id ? 'border-iv-cyan/50' : 'border-iv-border/50 hover:border-iv-border'}`}
                    onClick={() => setActiveTripId(trip.trip_id)}
                  >
                    <div className="p-2 rounded-full shrink-0 bg-iv-cyan/10">
                      <Car size={14} className="text-iv-cyan" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-iv-text truncate">
                        {getLocationName(trip.start_latitude, trip.start_longitude)} <span className="text-iv-muted">→</span> {getLocationName(trip.destination_latitude, trip.destination_longitude)}
                      </p>
                      <p className="text-[10px] text-iv-muted">{format(parseISO(trip.start_time), "MMM d, HH:mm")}</p>
                    </div>
                    <div className="text-right shrink-0">
                        <p className="text-xs font-bold text-iv-text">{trip.distance_km.toFixed(1)} km</p>
                    </div>
                  </div>
                ))}

                {visibleCount < currentMonthTrips.length && (
                  <button
                    onClick={() => setVisibleCount(prev => prev + 10)}
                    className="w-full py-3 mt-2 rounded-xl border border-dashed border-iv-border hover:border-iv-cyan hover:bg-iv-cyan/5 text-xs font-medium text-iv-muted hover:text-iv-cyan transition-all flex items-center justify-center gap-2"
                  >
                    Show More ({currentMonthTrips.length - visibleCount} remaining)
                  </button>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      {selectedMonth === null && (
        <div className="glass rounded-2xl p-12 text-center flex flex-col items-center gap-4">
          <Calendar className="text-iv-muted opacity-20" size={48} />
          <p className="text-sm text-iv-muted">Select a month above to view trips</p>
        </div>
      )}
    </div>
  );
}
