"use client";

import { useEffect, useState } from "react";
import { MapContainer, TileLayer, Marker, ZoomControl } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useTheme } from "next-themes";
import { getCartoTileUrl } from "@/lib/map-utils";

// Fix for default Leaflet markers in Next.js/Webpack
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

interface MapProps {
  latitude: number;
  longitude: number;
}

export default function LocationMap({ latitude, longitude }: MapProps) {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return <div className="w-full h-full bg-iv-surface/20 animate-pulse" />;

  const isDark = resolvedTheme === "dark";

  // CARTO Basemaps tiles — require an API key since CARTO gated the public
  // tile service. NEXT_PUBLIC_CARTO_BASEMAPS_API_KEY is inlined into the client
  // bundle at build time by Next.js. Get a free key at
  // https://carto.com/basemaps/apikey/. The CSP img-src directive already
  // permits https://*.basemaps.cartocdn.com (added in v1.1.2.1 PR #163).
  // CARTO Basemaps tile URL + API key wiring lives in getCartoTileUrl()
  // (frontend/src/lib/map-utils.ts) so all four map components stay in sync.
  const tileUrl = getCartoTileUrl(isDark);

  return (
    <div className="absolute inset-0 w-full h-full z-0 bg-[var(--iv-charcoal)]">
      <MapContainer
        center={[latitude, longitude]}
        zoom={14}
        zoomControl={false}
        scrollWheelZoom={false}
        dragging={true}
        style={{ width: "100%", height: "100%", background: isDark ? "#1C1C2E" : "#ffffff" }}
      >
        <TileLayer
          url={tileUrl}
          attribution='&copy; <a href="https://carto.com/attributions">CARTO</a>'
        />
        <ZoomControl position="bottomleft" />
        <Marker position={[latitude, longitude]} />
      </MapContainer>

      {/* Ensure zoom controls sit above the gradient overlays */}
      <style>{`
        .leaflet-control-zoom {
          z-index: 1000 !important;
          margin-bottom: 1rem !important;
          margin-left: 0.75rem !important;
        }
      `}</style>
      
      {/* Gradient overlay to smoothly blend with the car image section */}
      <div className="absolute inset-y-0 right-0 w-32 bg-gradient-to-l from-[var(--iv-charcoal)] to-transparent pointer-events-none z-[400] hidden lg:block" />
      <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-[var(--iv-charcoal)] to-transparent pointer-events-none z-[400] lg:hidden" />
    </div>
  );
}