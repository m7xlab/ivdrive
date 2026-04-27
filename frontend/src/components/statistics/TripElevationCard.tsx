"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Loader2, TrendingUp, TrendingDown, Mountain } from "lucide-react";

interface ElevationStats {
  trip_id: number;
  position_count: number;
  elevation_gain_m: number;
  elevation_loss_m: number;
  uphill_kwh: number;
  downhill_regen_kwh: number;
  net_kwh_per_100km: number;
  message: string;
}

interface TripElevationCardProps {
  vehicleId: string;
  tripId: number;
  distanceKm: number;
}

export function TripElevationCard({ vehicleId, tripId, distanceKm }: TripElevationCardProps) {
  const [stats, setStats] = useState<ElevationStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tripId) return;
    const fetchStats = async () => {
      try {
        setLoading(true);
        const res = await api.getTripElevationStats(vehicleId, tripId);
        setStats(res);
      } catch (err) {
        console.error("Failed to fetch elevation stats", err);
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, [vehicleId, tripId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 className="h-5 w-5 animate-spin text-iv-muted" />
      </div>
    );
  }

  if (!stats || stats.position_count < 2) {
    return null;
  }

  return (
    <div className="mt-4 bg-iv-surface/40 rounded-xl p-4 border border-iv-border/30 space-y-3">
      <div className="flex items-center gap-2 mb-2">
        <Mountain size={14} className="text-iv-cyan" />
        <h4 className="text-xs font-semibold text-iv-text uppercase tracking-wider">Elevation Stats</h4>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex items-center gap-2">
          <TrendingUp size={12} className="text-iv-red" />
          <span className="text-[11px] text-iv-muted">Uphill</span>
          <span className="text-xs font-bold text-iv-text ml-auto">
            {stats.elevation_gain_m.toFixed(0)}m
          </span>
        </div>
        <div className="flex items-center gap-2">
          <TrendingDown size={12} className="text-iv-green" />
          <span className="text-[11px] text-iv-muted">Downhill</span>
          <span className="text-xs font-bold text-iv-text ml-auto">
            {stats.elevation_loss_m.toFixed(0)}m
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Mountain size={12} className="text-iv-red" />
          <span className="text-[11px] text-iv-muted">Uphill energy</span>
          <span className="text-xs font-bold text-iv-text ml-auto">
            {stats.uphill_kwh.toFixed(2)} kWh
          </span>
        </div>
        <div className="flex items-center gap-2">
          <TrendingDown size={12} className="text-iv-green" />
          <span className="text-[11px] text-iv-muted">Regen gained</span>
          <span className="text-xs font-bold text-iv-text ml-auto">
            {stats.downhill_regen_kwh.toFixed(2)} kWh
          </span>
        </div>
      </div>

      <div className="pt-2 border-t border-iv-border/30 flex items-center justify-between">
        <span className="text-[10px] text-iv-muted">Net elevation penalty</span>
        <span className={`text-xs font-bold ${stats.net_kwh_per_100km > 0 ? "text-iv-red" : "text-iv-green"}`}>
          {stats.net_kwh_per_100km > 0 ? "+" : ""}{stats.net_kwh_per_100km.toFixed(2)} kWh/100km
        </span>
      </div>
    </div>
  );
}
