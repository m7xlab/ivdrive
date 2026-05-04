"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Loader2, Car, TrendingDown } from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
} from "recharts";

interface IceTcoTrip {
  trip_id: number;
  start_date: string | null;
  distance_km: number;
  kwh_consumed: number;
  ev_cost_eur: number;
  ice_cost_eur: number;
  savings_eur: number;
  cumulative_ev_cost_eur: number;
  cumulative_ice_cost_eur: number;
}

interface IceTcoResponse {
  trips: IceTcoTrip[];
  summary: {
    total_trips: number;
    total_distance_km: number;
    total_ev_cost_eur: number;
    total_ice_cost_eur: number;
    total_savings_eur: number;
    electricity_price_eur_kwh: number;
    petrol_price_eur_l: number;
  };
}

export function IceTcoDashboard({ vehicleId }: { vehicleId: string }) {
  const [data, setData] = useState<IceTcoResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const res = await api.getIceTco(vehicleId);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch ICE TCO", err);
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
          <Car className="h-5 w-5 text-iv-muted" />
          <h3 className="text-lg font-bold text-iv-text">ICE vs EV TCO Comparison</h3>
        </div>
        <p className="text-sm text-iv-text-muted">Not enough trip data for TCO comparison.</p>
      </div>
    );
  }

  const { summary } = data;

  // Cumulative chart data
  const cumulativeData = data.trips.map((t) => ({
    date: t.start_date ? new Date(t.start_date).toLocaleDateString() : "?",
    "EV Cumulative": t.cumulative_ev_cost_eur,
    "ICE Cumulative": t.cumulative_ice_cost_eur,
  }));

  // Per-trip savings
  const savingsData = data.trips.slice(-30).map((t) => ({
    date: t.start_date ? new Date(t.start_date).toLocaleDateString() : "?",
    savings: t.savings_eur,
    ev: t.ev_cost_eur,
    ice: t.ice_cost_eur,
  }));

  return (
    <div className="space-y-6 mt-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Trips Analyzed", value: summary.total_trips, color: "text-iv-text" },
          { label: "Total Distance", value: `${summary.total_distance_km} km`, color: "text-iv-text" },
          { label: "EV Cost", value: `${summary.total_ev_cost_eur} €`, color: "text-iv-cyan" },
          { label: "ICE Cost", value: `${summary.total_ice_cost_eur} €`, color: "text-iv-red" },
        ].map((item) => (
          <div key={item.label} className="glass rounded-xl border border-iv-border p-4 text-center">
            <p className="text-xs text-iv-text-muted uppercase tracking-wider">{item.label}</p>
            <p className={`text-xl font-bold mt-1 ${item.color}`}>{item.value}</p>
          </div>
        ))}
      </div>

      {/* Savings highlight */}
      <div className="glass rounded-xl border border-iv-green/30 bg-iv-green/5 p-4 text-center">
        <p className="text-sm text-iv-text">
          <span className="font-bold text-iv-green text-2xl">{summary.total_savings_eur} €</span>
          <span className="text-iv-text-muted ml-2">saved vs ICE ({summary.electricity_price_eur_kwh.toFixed(2)} €/kWh vs {summary.petrol_price_eur_l.toFixed(2)} €/L)</span>
        </p>
      </div>

      {/* Cumulative TCO comparison */}
      <div className="glass rounded-2xl border border-iv-border p-6">
        <h3 className="text-lg font-bold text-iv-text mb-4">Cumulative TCO: EV vs ICE over Time</h3>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={cumulativeData} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
              <XAxis dataKey="date" className="text-iv-muted text-xs" />
              <YAxis className="text-iv-muted text-xs" label={{ value: 'EUR', angle: -90, position: 'insideLeft', style: { fill: 'var(--iv-muted)' } }} />
              <Tooltip
                contentStyle={{ backgroundColor: "var(--iv-bg)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                itemStyle={{ color: "var(--iv-text)" }}
                formatter={(value: number, name: string) => [`${value.toFixed(2)} €`, name]}
              />
              <Legend wrapperStyle={{ paddingTop: "16px" }} />
              <Line type="monotone" dataKey="ICE Cumulative" stroke="var(--iv-red)" strokeWidth={2} strokeDasharray="5 5" name="ICE (fuel)" />
              <Line type="monotone" dataKey="EV Cumulative" stroke="var(--iv-cyan)" strokeWidth={2} name="EV (electric)" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Per-trip comparison */}
      <div className="glass rounded-2xl border border-iv-border p-6">
        <h3 className="text-lg font-bold text-iv-text mb-4">Per-Trip Cost Comparison (Recent 30)</h3>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={savingsData} margin={{ top: 10, right: 30, left: 0, bottom: 30 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
              <XAxis dataKey="date" className="text-iv-muted text-xs" angle={-45} textAnchor="end" interval={0} />
              <YAxis className="text-iv-muted text-xs" label={{ value: 'EUR', angle: -90, position: 'insideLeft', style: { fill: 'var(--iv-muted)' } }} />
              <Tooltip
                contentStyle={{ backgroundColor: "var(--iv-bg)", border: "1px solid var(--iv-border)", borderRadius: "8px" }}
                itemStyle={{ color: "var(--iv-text)" }}
                formatter={(value: number, name: string) => [`${value.toFixed(2)} €`, name]}
              />
              <Legend wrapperStyle={{ paddingTop: "16px" }} />
              <Bar dataKey="ice" fill="var(--iv-red)" name="ICE Cost" opacity={0.6} radius={[2, 2, 0, 0]} />
              <Bar dataKey="ev" fill="var(--iv-cyan)" name="EV Cost" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}