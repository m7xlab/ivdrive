"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Loader2, ThermometerSnowflake } from "lucide-react";

interface HVACMetric {
  band: string;
  representative_temp_celsius: number;
  avg_kwh_100km: number;
  reference_kwh_100km: number | null;
  hvac_cost_kwh_100km: number;
  trip_count: number;
  message: string;
}

interface HVACCostResponse {
  metrics: HVACMetric[];
  reference_band: string;
  reference_kwh_100km: number | null;
  summary: string;
}

function HVACCostCardInner({ vehicleId }: { vehicleId: string }) {
  const [data, setData] = useState<HVACCostResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const res = await api.getHVACCost(vehicleId);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch HVAC cost", err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [vehicleId]);

  if (loading) {
    return (
      <div className="glass p-5 rounded-2xl border border-iv-border flex items-center justify-center min-h-[120px]">
        <Loader2 className="h-6 w-6 animate-spin text-iv-muted" />
      </div>
    );
  }

  // Show the most impactful cold band
  const coldMetrics = data?.metrics.filter(m => m.hvac_cost_kwh_100km > 0) || [];
  const topMetric = coldMetrics.sort((a, b) => b.hvac_cost_kwh_100km - a.hvac_cost_kwh_100km)[0];

  if (!topMetric) {
    return (
      <div className="glass p-5 rounded-2xl border border-iv-border relative overflow-hidden group">
        <h3 className="text-sm font-medium text-iv-muted flex items-center gap-2 mb-1">
          <ThermometerSnowflake size={16} className="text-iv-cyan" /> HVAC Cost
        </h3>
        <p className="text-sm text-iv-muted">Not enough data to calculate HVAC cost.</p>
      </div>
    );
  }

  const cost = topMetric.hvac_cost_kwh_100km;
  const temp = Number(topMetric.representative_temp_celsius);

  return (
    <div className="glass p-5 rounded-2xl border border-iv-border relative overflow-hidden group">
      <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
        <ThermometerSnowflake size={80} className="text-iv-cyan" />
      </div>
      <h3 className="text-sm font-medium text-iv-muted flex items-center gap-2 mb-1">
        <ThermometerSnowflake size={16} className="text-iv-cyan" /> HVAC Cost
      </h3>
      <div className="flex items-baseline gap-2 mt-2">
        <span className="text-3xl font-bold text-iv-cyan">~{cost.toFixed(1)}</span>
        <span className="text-sm text-iv-muted">kWh/100km</span>
        <span className="text-sm text-iv-muted">at {temp.toFixed(0)}°C</span>
      </div>
      <div className="mt-3 flex flex-col gap-1 text-xs">
        <div className="flex justify-between">
          <span className="text-iv-muted">Band</span>
          <span className="font-mono text-iv-text">{topMetric.band}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-iv-muted">Trips analyzed</span>
          <span className="font-mono text-iv-text">{topMetric.trip_count}</span>
        </div>
      </div>
    </div>
  );
}

function HVACCostCard({ vehicleId }: { vehicleId: string }) {
  return <HVACCostCardInner vehicleId={vehicleId} />;
}

export { HVACCostCard };
export type { HVACCostResponse, HVACMetric };
