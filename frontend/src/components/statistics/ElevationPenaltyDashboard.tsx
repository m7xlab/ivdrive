"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Loader2, TrendingUp, TrendingDown, Mountain } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  LineChart,
  Line,
} from "recharts";

interface ElevationTrip {
  trip_id: number;
  start_date: string | null;
  distance_km: number;
  start_elevation_m: number;
  end_elevation_m: number;
  elevation_change_m: number;
  uphill_kwh_per_100km: number;
  downhill_kwh_per_100km: number;
  net_energy_kwh: number;
}

interface ElevationPenaltyResponse {
  trips: ElevationTrip[];
  summary: {
    total_trips: number;
    total_uphill_kwh: number;
    total_downhill_kwh: number;
    net_energy_kwh: number;
  };
}

export function ElevationPenaltyDashboard({ vehicleId }: { vehicleId: string }) {
  const [data, setData] = useState<ElevationPenaltyResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const res = await api.getElevationPenalty(vehicleId);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch elevation penalty", err);
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

  if (!data || data.trips.length === 0) {
    return (
      <div className="glass rounded-2xl border border-iv-border p-6 mt-6">
        <div className="flex items-center gap-2 mb-2">
          <Mountain className="h-5 w-5 text-iv-muted" />
          <h3 className="text-lg font-bold text-iv-text">Elevation Penalty & Regen</h3>
        </div>
        <p className="text-sm text-iv-text-muted">Not enough trips with elevation data for analysis.</p>
      </div>
    );
  }

  const chartData = data.trips.map((t) => ({
    date: t.start_date ? new Date(t.start_date).toLocaleDateString() : "?",
    distance: t.distance_km,
    uphill: t.uphill_kwh_per_100km,
    downhill: t.downhill_kwh_per_100km,
    net: t.net_energy_kwh,
    elev_change: t.elevation_change_m,
  }));

  const s = data.summary;

  return (
    <div className="space-y-6 mt-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Trips Analyzed", value: s.total_trips, color: "text-iv-text" },
          { label: "Uphill Cost", value: `${s.total_uphill_kwh} kWh`, color: "text-iv-red" },
          { label: "Regen Gained", value: `${s.total_downhill_kwh} kWh`, color: "text-iv-green" },
          { label: "Net Cost", value: `${s.net_energy_kwh} kWh`, color: s.net_energy_kwh > 0 ? "text-iv-red" : "text-iv-green" },
        ].map((item) => (
          <div key={item.label} className="glass rounded-xl border border-iv-border p-4 text-center">
            <p className="text-xs text-iv-text-muted uppercase tracking-wider">{item.label}</p>
            <p className={`text-xl font-bold mt-1 ${item.color}`}>{item.value}</p>
          </div>
        ))}
      </div>

      {/* Energy breakdown chart */}
      <div className="glass rounded-2xl border border-iv-border p-6">
        <h3 className="text-lg font-bold text-iv-text mb-4">Uphill vs Downhill Energy per Trip</h3>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
              <XAxis dataKey="date" className="text-iv-muted text-xs" />
              <YAxis className="text-iv-muted text-xs" label={{ value: 'kWh/100km', angle: -90, position: 'insideLeft', style: { fill: 'var(--iv-muted)' } }} />
              <Tooltip
                contentStyle={{ backgroundColor: "var(--iv-bg)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                itemStyle={{ color: "var(--iv-text)" }}
              />
              <Legend wrapperStyle={{ paddingTop: "16px" }} />
              <Bar dataKey="uphill" stackId="a" fill="var(--iv-red)" name="Uphill Cost" radius={[0, 0, 4, 4]} />
              <Bar dataKey="downhill" stackId="a" fill="var(--iv-green)" name="Regen Gained" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Elevation change chart */}
      <div className="glass rounded-2xl border border-iv-border p-6">
        <h3 className="text-lg font-bold text-iv-text mb-4">Net Elevation Change per Trip (m)</h3>
        <div className="h-48 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
              <XAxis dataKey="date" className="text-iv-muted text-xs" />
              <YAxis className="text-iv-muted text-xs" />
              <Tooltip
                contentStyle={{ backgroundColor: "var(--iv-bg)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                itemStyle={{ color: "var(--iv-text)" }}
              />
              <Line type="monotone" dataKey="elev_change" stroke="var(--iv-cyan)" strokeWidth={2} dot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}