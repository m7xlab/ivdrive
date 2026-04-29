
"use client";

import { useState, useEffect } from "react";
import { Bolt, MapPin, Cloud, Clock } from "lucide-react";
import { api } from "@/lib/api";
import { formatSmartDuration } from "@/lib/format";

interface PulseData {
  status: string;
  battery_pct: number;
  remaining_range_km: number;
  temperature_celsius: number | null;
  weather_code: string | null;
  is_online: boolean;
  charging_power_kw: number;
  remaining_charge_time_min: number;
}

export function PulseDashboard({ vehicleId }: { vehicleId: string }) {
  const [pulse, setPulse] = useState<PulseData | null>(null);

  useEffect(() => {
    const fetchPulse = async () => {
      try {
        const data = await api.getAnalyticsPulse(vehicleId);
        setPulse(data);
      } catch (err) {
        console.error("Failed to fetch live pulse", err);
      }
    };
    fetchPulse();
    const interval = setInterval(fetchPulse, 30000); // 30s refresh
    return () => clearInterval(interval);
  }, [vehicleId]);

  if (!pulse) return <div className="animate-pulse h-32 bg-iv-surface rounded-2xl border border-iv-border mt-6" />;

  const isCharging = pulse.status === "CHARGING" || pulse.status === "READY_FOR_CHARGING";
  const isOnline = pulse.is_online;

  return (
    <div className="glass rounded-2xl border border-iv-border p-6 mt-6">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h3 className="text-lg font-bold text-iv-text flex items-center gap-2">
            <Bolt className="w-5 h-5 text-iv-green" />
            Live Pulse Telemetry
          </h3>
          <p className="text-sm text-iv-text-muted">Real-time status updates</p>
        </div>
        <div className={`px-3 py-1 rounded-full text-xs font-semibold ${isOnline ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"}`}>
          {isOnline ? "• ONLINE" : "OFFLINE"}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        
        <div className="bg-iv-surface rounded-xl p-5 border border-iv-border/50">
          <p className="text-sm text-iv-text-muted flex items-center gap-2 mb-3">
            <Bolt className="w-4 h-4 text-iv-green" /> State of Charge
          </p>
          <p className="text-3xl font-bold text-iv-text">{pulse.battery_pct}<span className="text-lg font-normal text-iv-text-muted">%</span></p>
          <div className="w-full bg-iv-charcoal h-2 rounded-full mt-4 overflow-hidden">
            <div className="bg-iv-green h-full" style={{ width: `${pulse.battery_pct}%` }} />
          </div>
        </div>

        <div className="bg-iv-surface rounded-xl p-5 border border-iv-border/50">
          <p className="text-sm text-iv-text-muted flex items-center gap-2 mb-3">
            <MapPin className="w-4 h-4 text-iv-cyan" /> Est. Full Range
          </p>
          <p className="text-3xl font-bold text-iv-text">{pulse.remaining_range_km}<span className="text-lg font-normal text-iv-text-muted">km</span></p>
          {pulse.battery_pct > 0 && (
            <p className="text-xs text-iv-text-muted mt-4">
              Calculated Max: <span className="text-iv-text">{Math.round((pulse.remaining_range_km / pulse.battery_pct) * 100)} km</span>
            </p>
          )}
        </div>

        {isCharging ? (
          <div className="bg-iv-surface rounded-xl p-5 border border-emerald-500/30">
            <p className="text-sm text-iv-text-muted flex items-center gap-2 mb-3">
              <Clock className="w-4 h-4 text-emerald-400" /> Charging Speed
            </p>
            <p className="text-3xl font-bold text-iv-text">{pulse.charging_power_kw}<span className="text-lg font-normal text-iv-text-muted">kW</span></p>
            <p className="text-xs text-iv-text-muted mt-4 text-emerald-400">
              {formatSmartDuration(pulse.remaining_charge_time_min)} to target
            </p>
          </div>
        ) : (
          <div className="bg-iv-surface rounded-xl p-5 border border-iv-border/50">
            <p className="text-sm text-iv-text-muted flex items-center gap-2 mb-3">
              <MapPin className="w-4 h-4 text-iv-text-muted" /> Motion Status
            </p>
            <p className="text-xl font-bold text-iv-text mt-3">{pulse.status}</p>
          </div>
        )}

        <div className="bg-iv-surface rounded-xl p-5 border border-iv-border/50">
          <p className="text-sm text-iv-text-muted flex items-center gap-2 mb-3">
            <Cloud className="w-4 h-4 text-amber-500" /> Local Weather
          </p>
          <p className="text-3xl font-bold text-iv-text">
            {pulse.temperature_celsius !== null ? `${pulse.temperature_celsius}°` : "--"}
          </p>
          <p className="text-xs text-iv-text-muted mt-4">Ambient Temp</p>
        </div>

      </div>
    </div>
  );
}
