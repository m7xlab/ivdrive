"use client";

import { useEffect, useState, useCallback } from "react";
import { MapPin, Loader2, Zap } from "lucide-react";
import "leaflet/dist/leaflet.css";
import { api } from "@/lib/api";
import type { TimelineRange } from "./StatisticsShell";

export interface VisitedDashboardProps {
  vehicleId: string;
  dateRange: TimelineRange;
}

interface VisitedLocation {
  latitude: number;
  longitude: number;
  timestamp: string;
  source: string;
}

function toISO(d: Date) {
  return d.toISOString();
}

export function VisitedDashboard({ vehicleId, dateRange }: VisitedDashboardProps) {
  const [locations, setLocations] = useState<VisitedLocation[]>([]);
  const [loading, setLoading] = useState(true);

  const fromISO = toISO(dateRange.from);
  const toISOVal = toISO(dateRange.to);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.getVisitedLocations(vehicleId, 2000, fromISO, toISOVal);
      setLocations(list ?? []);
    } catch {
      setLocations([]);
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
        <p className="text-sm text-iv-muted">Loading visited locations...</p>
      </div>
    );
  }

  if (locations.length === 0) {
    return (
      <div className="glass rounded-xl p-12 text-center">
        <MapPin size={32} className="mx-auto mb-3 text-iv-muted" />
        <p className="text-sm text-iv-muted">No position data for this period.</p>
      </div>
    );
  }

  const posCount = locations.filter((l) => l.source === "position").length;
  const chargeCount = locations.filter((l) => l.source === "charging").length;

  return (
    <div className="glass rounded-xl overflow-hidden">
      <div className="p-3 border-b border-iv-border flex items-center gap-4 text-sm text-iv-muted">
        <span className="flex items-center gap-1.5">
          <MapPin size={16} />
          {posCount} position{posCount !== 1 ? "s" : ""}
        </span>
        {chargeCount > 0 && (
          <span className="flex items-center gap-1.5">
            <Zap size={16} className="text-green-400" />
            {chargeCount} charging location{chargeCount !== 1 ? "s" : ""}
          </span>
        )}
      </div>
      <div className="h-[calc(100vh-280px)] min-h-[400px] w-full relative bg-iv-surface/30">
        <VisitedMap locations={locations} />
      </div>
    </div>
  );
}

interface VisitedMapProps {
  locations: VisitedLocation[];
}

function VisitedMap({ locations }: VisitedMapProps) {
  const [MapComponents, setMapComponents] = useState<{
    MapContainer: any;
    TileLayer: any;
    CircleMarker: any;
    Popup: any;
    ZoomControl: any;
  } | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    import("react-leaflet").then((LReact) => {
      setMapComponents({
        MapContainer: LReact.MapContainer,
        TileLayer: LReact.TileLayer,
        CircleMarker: LReact.CircleMarker,
        Popup: LReact.Popup,
        ZoomControl: LReact.ZoomControl,
      });
    });
  }, [mounted]);

  if (!MapComponents || locations.length === 0) {
    return (
      <div className="absolute inset-0 flex items-center justify-center text-iv-muted text-sm">
        {!MapComponents ? "Loading map…" : "No points to show"}
      </div>
    );
  }

  const { MapContainer, TileLayer, CircleMarker, Popup, ZoomControl } = MapComponents;
  const latSum = locations.reduce((a, p) => a + p.latitude, 0);
  const lonSum = locations.reduce((a, p) => a + p.longitude, 0);
  const center: [number, number] = [
    latSum / locations.length,
    lonSum / locations.length,
  ];

  const tileUrl =
    "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";

  return (
    <div className="absolute inset-0 z-0">
      <MapContainer
        center={center}
        zoom={10}
        scrollWheelZoom={true}
        zoomControl={false}
        style={{ width: "100%", height: "100%", background: "#1C1C2E" }}
      >
        <TileLayer
          url={tileUrl}
          attribution='&copy; <a href="https://carto.com/attributions">CARTO</a>'
        />
        <ZoomControl position="bottomleft" />
        {locations.map((loc, i) => {
          const isCharging = loc.source === "charging";
          const color = isCharging ? "#4ade80" : "#60a5fa";
          const radius = isCharging ? 7 : 4;
          const ts = new Date(loc.timestamp);
          return (
            <CircleMarker
              key={`${loc.timestamp}-${i}`}
              center={[loc.latitude, loc.longitude]}
              radius={radius}
              pathOptions={{
                color,
                fillColor: color,
                fillOpacity: 0.7,
                weight: 1,
              }}
            >
              <Popup>
                <div className="text-xs">
                  <div className="font-medium">{isCharging ? "⚡ Charging" : "📍 Position"}</div>
                  <div>{ts.toLocaleDateString()} {ts.toLocaleTimeString()}</div>
                  <div className="text-gray-400">
                    {loc.latitude.toFixed(5)}, {loc.longitude.toFixed(5)}
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}
