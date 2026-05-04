"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Loader2, Battery, Euro } from "lucide-react";

interface VampireDrainResponse {
  avg_drain_pct_per_hour: number;
  avg_drain_pct_per_day: number;
  drain_kwh_per_day: number;
  drain_kwh_per_week: number;
  drain_kwh_per_month: number;
  electricity_price_eur_kwh: number;
  cost_per_day_eur: number;
  cost_per_week_eur: number;
  cost_per_month_eur: number;
  battery_capacity_kwh: number;
}

export function VampireDrainDashboard({ vehicleId }: { vehicleId: string }) {
  const [data, setData] = useState<VampireDrainResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const res = await api.getVampireDrain(vehicleId);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch vampire drain", err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [vehicleId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 glass rounded-2xl border border-iv-border p-6 mt-6">
        <Loader2 className="h-8 w-8 animate-spin text-iv-muted" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="glass rounded-2xl border border-iv-border p-6 mt-6">
        <div className="flex items-center gap-2 mb-2">
          <Battery className="h-5 w-5 text-iv-muted" />
          <h3 className="text-lg font-bold text-iv-text">Vampire Drain Analysis</h3>
        </div>
        <p className="text-sm text-iv-text-muted">No vehicle state data for drain analysis.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 mt-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Drain Rate", value: `${data.avg_drain_pct_per_day}%/day`, sub: `${data.avg_drain_pct_per_hour}%/hr`, color: "text-iv-yellow" },
          { label: "Daily Loss", value: `${data.drain_kwh_per_day} kWh`, sub: `@ ${data.electricity_price_eur_kwh}€/kWh`, color: "text-iv-text" },
          { label: "Weekly Cost", value: `${data.cost_per_week_eur} €`, sub: `${data.drain_kwh_per_week} kWh`, color: "text-iv-text" },
          { label: "Monthly Cost", value: `${data.cost_per_month_eur} €`, sub: `${data.drain_kwh_per_month} kWh`, color: "text-iv-text" },
        ].map((item) => (
          <div key={item.label} className="glass rounded-xl border border-iv-border p-4 text-center">
            <p className="text-xs text-iv-text-muted uppercase tracking-wider">{item.label}</p>
            <p className={`text-xl font-bold mt-1 ${item.color}`}>{item.value}</p>
            <p className="text-xs text-iv-muted">{item.sub}</p>
          </div>
        ))}
      </div>

      {/* Cost breakdown */}
      <div className="glass rounded-2xl border border-iv-border p-6">
        <h3 className="text-lg font-bold text-iv-text mb-4">Vampire Drain Cost Over Time</h3>
        <div className="grid grid-cols-3 gap-6 text-center">
          <div>
            <p className="text-xs text-iv-text-muted uppercase tracking-wider mb-1">Per Day</p>
            <p className="text-2xl font-bold text-iv-text">{data.cost_per_day_eur} €</p>
            <p className="text-xs text-iv-muted mt-1">{data.drain_kwh_per_day} kWh lost</p>
          </div>
          <div>
            <p className="text-xs text-iv-text-muted uppercase tracking-wider mb-1">Per Week</p>
            <p className="text-2xl font-bold text-iv-cyan">{data.cost_per_week_eur} €</p>
            <p className="text-xs text-iv-muted mt-1">{data.drain_kwh_per_week} kWh lost</p>
          </div>
          <div>
            <p className="text-xs text-iv-text-muted uppercase tracking-wider mb-1">Per Month</p>
            <p className="text-2xl font-bold text-iv-red">{data.cost_per_month_eur} €</p>
            <p className="text-xs text-iv-muted mt-1">{data.drain_kwh_per_month} kWh lost</p>
          </div>
        </div>
        <div className="mt-6 pt-4 border-t border-iv-border">
          <p className="text-sm text-iv-text-muted">
            <span className="font-bold text-iv-text">{data.avg_drain_pct_per_day}% of your {data.battery_capacity_kwh} kWh battery</span> is lost
            per day to vampire drain (systems, standby, etc.).
            Over a year, this costs approximately <span className="text-iv-yellow">{Number(data.cost_per_month_eur * 12).toFixed(2)} €</span>.
          </p>
        </div>
      </div>
    </div>
  );
}