"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Loader2 } from "lucide-react";

interface HVACMetric {
  speed_profile: string;
  avg_speed_desc: string;
  cold_trips: number;
  optimal_trips: number;
  optimal_kwh_100km: number;
  cold_kwh_100km: number;
  hvac_cost_kwh_100km: number;
  message: string;
}

interface HVACResponse {
  metrics: HVACMetric[];
  summary: string;
}

export function HVACIsolationDashboard({ vehicleId }: { vehicleId: string }) {
  const [data, setData] = useState<HVACResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchHVAC = async () => {
      try {
        setLoading(true);
        // Replace with actual API call if needed
        const res = await api.getHVACIsolation(vehicleId);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch HVAC isolation data", err);
      } finally {
        setLoading(false);
      }
    };
    fetchHVAC();
  }, [vehicleId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 glass rounded-2xl border border-iv-border p-6 mt-6">
        <Loader2 className="h-8 w-8 animate-spin text-iv-muted" />
      </div>
    );
  }

  if (!data || data.metrics.length === 0) {
    return (
      <div className="glass rounded-2xl border border-iv-border p-6 mt-6">
        <h3 className="text-lg font-bold text-iv-text mb-2">HVAC Isolation</h3>
        <p className="text-sm text-iv-text-muted">Not enough trips to calculate HVAC costs across temperature brackets.</p>
      </div>
    );
  }

  return (
    <div className="glass rounded-2xl border border-iv-border p-6 mt-6">
      <h3 className="text-lg font-bold text-iv-text">HVAC Isolation</h3>
      <p className="text-sm text-iv-text-muted mb-6">{data.summary}</p>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {data.metrics.map((m, idx) => (
          <div key={m.speed_profile} className="bg-white/5 border border-iv-border rounded-xl p-4">
            <h4 className="text-iv-accent font-semibold mb-2 capitalize">{m.speed_profile} ({m.avg_speed_desc})</h4>
            <div className="flex flex-col gap-2 text-sm text-iv-text">
              <div className="flex justify-between">
                <span className="text-iv-text-muted">Optimal (15-25°C):</span>
                <span>{m.optimal_kwh_100km} kWh</span>
              </div>
              <div className="flex justify-between">
                <span className="text-iv-text-muted">Cold (≤5°C):</span>
                <span>{m.cold_kwh_100km} kWh</span>
              </div>
              <div className="flex justify-between font-bold border-t border-iv-border pt-2 mt-1">
                <span className="text-iv-primary">HVAC Cost:</span>
                <span className="text-iv-primary">{m.hvac_cost_kwh_100km} kWh/100km</span>
              </div>
            </div>
            <p className="text-xs text-iv-text-muted mt-4 italic">{m.message}</p>
            <div className="text-xs text-iv-text-muted/50 mt-2">Based on {m.cold_trips} cold / {m.optimal_trips} opt trips</div>
          </div>
        ))}
      </div>
    </div>
  );
}
