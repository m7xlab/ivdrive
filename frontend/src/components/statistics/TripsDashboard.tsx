
"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { format, parseISO, getYear, getMonth } from "date-fns";
import { Loader2, Car, Clock, Calendar, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import { MapContainer, TileLayer, Polyline, useMap } from 'react-leaflet';
import "leaflet/dist/leaflet.css";

// --- Types ---
export interface TripsDashboardProps {
  vehicleId: string;
  dateRange?: { from: Date; to: Date }; // Statistics page usage
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

// --- Helper Components ---
function MapAutoBounds({ trips }: { trips: TripAnalyticsItem[] }) {
  const map = useMap();
  useEffect(() => {
    if (trips.length === 0) return;
    const bounds: [number, number][] = [];
    trips.forEach(t => {
      const pos = getPolylinePositions(t);
      if (pos) {
        bounds.push(pos[0], pos[1]);
      }
    });
    if (bounds.length > 0) map.fitBounds(bounds, { padding: [30, 30], animate: false });
  }, [trips, map]);
  return null;
}

function MapController({ activeTripId, trips }: { activeTripId: number | null, trips: TripAnalyticsItem[] }) {
    const map = useMap();
    useEffect(() => {
        const activeTrip = trips.find(t => t.trip_id === activeTripId);
        const pos = activeTrip ? getPolylinePositions(activeTrip) : null;
        if (pos) {
            map.flyTo(pos[0], 13, { animate: false });
        }
    }, [activeTripId, trips, map]);
    return null;
}

function formatDuration(minutes: number): string {
  if (minutes <= 0) return "—";
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

/** Returns true only if the value is a valid number for lat/lng (not null, undefined, or NaN). */
function isValidCoord(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/** Builds a Polyline positions array only when both start and end are valid; otherwise returns null. */
function getPolylinePositions(trip: TripAnalyticsItem): [[number, number], [number, number]] | null {
  if (
    !isValidCoord(trip.start_latitude) ||
    !isValidCoord(trip.start_longitude) ||
    !isValidCoord(trip.destination_latitude) ||
    !isValidCoord(trip.destination_longitude)
  ) {
    return null;
  }
  return [
    [trip.start_latitude, trip.start_longitude],
    [trip.destination_latitude, trip.destination_longitude],
  ];
}

// --- Main Component ---
export function TripsDashboard({ vehicleId, dateRange }: TripsDashboardProps) {
  const [allTrips, setAllTrips] = useState<TripAnalyticsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTripId, setActiveTripId] = useState<number | null>(null);
  const [locations, setLocations] = useState<Map<string, string>>(new Map());
  
  // Year/Month selection
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [selectedMonth, setSelectedMonth] = useState<number | null>(null);
  const [visibleCount, setVisibleCount] = useState(10);

  // Geocoding helper
  const fetchLocationName = useCallback(async (lat: number, lon: number) => {
    try {
      const data = await api.reverseGeocode(lat, lon);
      return data.display_name || "Location";
    } catch {
      return "Location";
    }
  }, []);

  const getLocationName = (lat: number | null | undefined, lon: number | null | undefined) => {
    if (lat == null || lon == null) return "Location";
    const key = `${lat.toFixed(5)},${lon.toFixed(5)}`;
    return locations.get(key) || "Location";
  };

  // Initial load
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const fromStr = dateRange?.from?.toISOString();
        const toStr = dateRange?.to?.toISOString();
        const limit = dateRange ? 200 : 2000;
        const list = await api.getTripsAnalytics(vehicleId, limit, fromStr, toStr);
        setAllTrips(list ?? []);
        
        if (!dateRange && list && list.length > 0) {
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
    fetchData();
  }, [vehicleId, dateRange?.from, dateRange?.to]);

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

  // Filtered trips
  const displayTrips = useMemo(() => {
    if (dateRange) return allTrips;
    if (selectedMonth === null || selectedYear === null) return [];
    return allTrips.filter(t => {
      const d = parseISO(t.start_time);
      return getYear(d) === selectedYear && getMonth(d) === selectedMonth;
    });
  }, [allTrips, selectedYear, selectedMonth, dateRange]);

  const visibleTrips = useMemo(() => {
    if (dateRange) return displayTrips;
    return displayTrips.slice(0, visibleCount);
  }, [displayTrips, visibleCount, dateRange]);

  const summary = useMemo(() => {
    const validTrips = displayTrips.filter(t => t.distance_km > 0 && t.kwh_used != null && t.kwh_used > 0);
    const totalDist = validTrips.reduce((acc, t) => acc + (t.distance_km || 0), 0);
    const totalKwh = validTrips.reduce((acc, t) => acc + (t.kwh_used || 0), 0);
    const calculatedEff = totalDist > 0 ? (totalKwh / totalDist) * 100 : 0;

    return {
      totalTrips: displayTrips.length,
      totalDistance: displayTrips.reduce((acc, trip) => acc + (trip.distance_km || 0), 0),
      totalTime: displayTrips.reduce((acc, trip) => acc + (trip.duration_minutes || 0), 0),
      avgEfficiency: calculatedEff
    };
  }, [displayTrips]);

  // Lazy geocoding
  useEffect(() => {
    let isMounted = true;
    const newLocations = new Map(locations);
    let changed = false;

    const resolve = async () => {
      for (const trip of visibleTrips) {
        if (!isMounted) break;
        const coords = [
          { lat: trip.start_latitude, lon: trip.start_longitude },
          { lat: trip.destination_latitude, lon: trip.destination_longitude }
        ];
        for (const { lat, lon } of coords) {
          if (lat == null || lon == null) continue;
          const key = `${lat.toFixed(5)},${lon.toFixed(5)}`;
          
          if (!newLocations.has(key)) {
            // Check session storage first to avoid API calls on refresh
            const cached = sessionStorage.getItem(`geo_${key}`);
            if (cached) {
              newLocations.set(key, cached);
              changed = true;
            } else {
              const name = await fetchLocationName(lat, lon);
              if (!isMounted) break;
              newLocations.set(key, name);
              sessionStorage.setItem(`geo_${key}`, name);
              changed = true;
            }
          }
        }
      }
      if (isMounted && changed) setLocations(newLocations);
    };
    resolve();
    
    return () => {
      isMounted = false;
    };
  }, [visibleTrips, fetchLocationName]);

  if (loading) {
    return <div className="flex items-center justify-center py-24"><Loader2 className="h-8 w-8 animate-spin text-iv-muted" /></div>;
  }

  if (allTrips.length === 0) {
    return <div className="py-24 text-center text-sm text-iv-muted">No trips recorded for the selected period.</div>;
  }

  return (
    <div className="space-y-6">
      {/* --- STATISTICS MODE: SHOW SUMMARY CARDS --- */}
      {dateRange && (
        <div className="glass rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-iv-text">Trip Summary</h3>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="bg-iv-surface/60 rounded-xl p-4 border border-iv-border/50">
              <p className="text-[10px] font-bold text-iv-muted uppercase mb-1">Total Trips</p>
              <p className="text-2xl font-bold text-iv-text">{summary.totalTrips}</p>
            </div>
            <div className="bg-iv-surface/60 rounded-xl p-4 border border-iv-border/50">
              <p className="text-[10px] font-bold text-iv-muted uppercase mb-1">Total Distance</p>
              <p className="text-2xl font-bold text-iv-text">{summary.totalDistance.toFixed(1)} km</p>
            </div>
            <div className="bg-iv-surface/60 rounded-xl p-4 border border-iv-border/50">
              <p className="text-[10px] font-bold text-iv-muted uppercase mb-1">Total Time</p>
              <p className="text-2xl font-bold text-iv-text">{formatDuration(summary.totalTime)}</p>
            </div>
            <div className="bg-iv-surface/60 rounded-xl p-4 border border-iv-cyan/30">
              <p className="text-[10px] font-bold text-iv-cyan uppercase mb-1 tracking-wider">Avg. Efficiency</p>
              <p className="text-2xl font-bold text-iv-cyan">{summary.avgEfficiency > 0 ? summary.avgEfficiency.toFixed(2) : '—'}</p>
              {summary.avgEfficiency > 0 && <p className="text-[10px] text-iv-muted mt-1">kWh/100km</p>}
            </div>
          </div>
        </div>
      )}

      {/* --- YEAR & MONTH NAVIGATION (Overview Mode) --- */}
      {!dateRange && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {structure.map(({ year }) => (
              <button
                key={year}
                onClick={() => { setSelectedYear(year); setVisibleCount(10); }}
                className={`px-4 py-2 rounded-xl text-sm font-bold transition-all border ${selectedYear === year ? 'bg-iv-cyan text-iv-surface border-iv-cyan' : 'bg-iv-surface/40 text-iv-text border-iv-border/50 hover:border-iv-cyan/50'}`}
              >
                {year}
              </button>
            ))}
          </div>
          
          {selectedYear && (
            <div className="flex flex-wrap gap-2 animate-in fade-in slide-in-from-top-1">
              {structure.find(s => s.year === selectedYear)?.months.map(m => (
                <button
                  key={m}
                  onClick={() => { setSelectedMonth(m); setVisibleCount(10); }}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${selectedMonth === m ? 'bg-iv-cyan/20 text-iv-cyan border border-iv-cyan/30' : 'bg-iv-surface/20 text-iv-muted border border-iv-border/30 hover:text-iv-text'}`}
                >
                  {MONTHS[m]}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* --- MAIN DASHBOARD: MAP + LIST (Only if month selected or in stats mode) --- */}
      {(dateRange || selectedMonth !== null) ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 glass rounded-2xl overflow-hidden h-[400px] lg:h-[500px] border border-iv-border/50">
            <MapContainer 
              center={[54.6872, 25.2797]} 
              zoom={13} 
              className="h-full w-full"
              scrollWheelZoom={true}
            >
              <TileLayer
                attribution='&copy; <a href="https://carto.com/attributions">CARTO</a>'
                url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              />
              {displayTrips.map(trip => {
                const positions = getPolylinePositions(trip);
                if (!positions) return null;
                const isActive = trip.trip_id === activeTripId;
                return (
                    <Polyline
                      key={trip.trip_id}
                      positions={positions}
                      pathOptions={{
                        color: isActive ? "#00f3ff" : "#475569",
                        weight: isActive ? 4 : 2,
                        opacity: isActive ? 1.0 : 0.6
                      }}
                      onClick={() => setActiveTripId(trip.trip_id)}
                    />
                )
              })}
              <MapAutoBounds trips={displayTrips} />
              <MapController activeTripId={activeTripId} trips={displayTrips} />
            </MapContainer>
          </div>

          <div className="glass rounded-2xl p-4 flex flex-col h-[400px] lg:h-[500px]">
            <h3 className="text-sm font-semibold text-iv-text mb-4">Trips</h3>
            <div className="flex-1 space-y-2 overflow-y-auto no-scrollbar pr-1">
              {visibleTrips.map((trip) => {
                const isActive = trip.trip_id === activeTripId;
                return (
                    <div
                      key={trip.trip_id}
                      className={`flex items-center gap-3 p-3 rounded-xl bg-iv-surface/60 border transition-all cursor-pointer ${isActive ? 'border-iv-cyan/50 bg-iv-cyan/5' : 'border-iv-border/40 hover:border-iv-border'}`}
                      onClick={() => setActiveTripId(trip.trip_id)}
                    >
                      <div className="p-2 rounded-full shrink-0 bg-iv-cyan/10">
                        <Car size={14} className={`text-iv-cyan ${isActive ? 'animate-pulse' : ''}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-iv-text truncate">
                          {getLocationName(trip.start_latitude, trip.start_longitude)} <span className="text-iv-muted">→</span> {getLocationName(trip.destination_latitude, trip.destination_longitude)}
                        </p>
                        <p className="text-[10px] text-iv-muted">{format(parseISO(trip.start_time), "MMM d, HH:mm")}</p>
                      </div>
                      <div className="text-right shrink-0">
                          <p className="text-xs font-bold text-iv-text">{trip.distance_km?.toFixed(1) ?? "0.0"} km</p>
                          <p className="text-[9px] text-iv-cyan font-medium">{trip.efficiency_kwh_100km?.toFixed(1) ?? "—"} kWh/100</p>
                      </div>
                    </div>
                )
              })}

              {!dateRange && selectedMonth !== null && visibleCount < displayTrips.length && (
                <button
                  onClick={() => setVisibleCount(prev => prev + 10)}
                  className="w-full py-3 mt-2 rounded-xl border border-dashed border-iv-border hover:border-iv-cyan hover:bg-iv-cyan/5 text-xs font-medium text-iv-muted hover:text-iv-cyan transition-all flex items-center justify-center gap-2"
                >
                  Show More ({displayTrips.length - visibleCount} remaining)
                </button>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="glass rounded-3xl p-20 text-center flex flex-col items-center gap-4 border-dashed">
          <Calendar className="text-iv-muted opacity-10" size={64} />
          <p className="text-sm text-iv-muted font-medium">Select a month above to view your trip history</p>
        </div>
      )}
    </div>
  );
}
