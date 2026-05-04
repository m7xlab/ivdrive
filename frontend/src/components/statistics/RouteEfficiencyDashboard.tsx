"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Loader2, Map, Route } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts";

interface RouteData {
  route_key: string;
  start_location: string;
  end_location: string;
  trip_count: number;
  avg_kwh_100km: number;
  min_kwh_100km: number;
  max_kwh_100km: number;
  avg_temp_celsius: number | null;
  total_distance_km: number;
  efficiency_score: number;
}

interface RouteEfficiencyResponse {
  routes: RouteData[];
  total_routes: number;
}

export function RouteEfficiencyDashboard({ vehicleId }: { vehicleId: string }) {
  const [data, setData] = useState<RouteEfficiencyResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const res = await api.getRouteEfficiency(vehicleId);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch route efficiency", err);
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

  if (!data || data.routes.length === 0) {
    return (
      <div className="glass rounded-2xl border border-iv-border p-6 mt-6">
        <div className="flex items-center gap-2 mb-2">
          <Route className="h-5 w-5 text-iv-muted" />
          <h3 className="text-lg font-bold text-iv-text">Route Efficiency Profiling</h3>
        </div>
        <p className="text-sm text-iv-text-muted">Not enough trips with location data for route analysis.</p>
      </div>
    );
  }

  // Truncate route label to first line (street name only), cap length
  const truncateRoute = (label: string, maxLen = 28) => {
    const firstLine = label.split("\n")[0];
    return firstLine.length > maxLen ? firstLine.slice(0, maxLen - 1) + "…" : firstLine;
  };


  const chartData = data.routes.slice(0, 15).map((r) => ({
    route: truncateRoute(r.route_key, 22),
    fullRoute: r.route_key.split("->").join(" → "),
    avg: r.avg_kwh_100km,
    score: r.efficiency_score,
    trips: r.trip_count,
    distance: r.total_distance_km,
  }));


  // Color: green≥70 / yellow≥40 / red<40 — always dark enough for both modes
  const getBarColor = (score: number) => {
    if (score >= 70) return "#22c55e";
    if (score >= 40) return "#eab308";
    return "#ef4444";
  };

  return (
    <div className="space-y-6 mt-6">
      <div className="glass rounded-2xl border border-iv-border p-6">
        <div className="flex items-center gap-2 mb-2">
          <Map className="h-5 w-5 text-iv-cyan" />
          <h3 className="text-lg font-bold text-iv-text">Route Efficiency Profiling</h3>
        </div>
        <p className="text-sm text-iv-text-muted mb-6">
          Top {Math.min(data.routes.length, 20)} routes by trip frequency. Efficiency Score: 100 = best (lowest kWh/100km).
        </p>

        {/* Top 20 routes bar chart */}
        <div className="h-96 w-full mb-8">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical" margin={{ top: 8, right: 20, left: 140, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-iv-border" />
              <XAxis type="number" className="text-iv-muted text-xs" domain={[0, "auto"]} label={{ value: 'kWh/100km', position: 'insideBottom', style: { fill: 'var(--iv-muted)', fontSize: 11 } }} />
              <YAxis type="category" dataKey="route" className="text-iv-muted text-[10px]" width={130} tick={{ fontSize: 10 }} />
              <Tooltip
                contentStyle={{ backgroundColor: "#ffffff", border: "1px solid #d8dce6", borderRadius: "8px", color: "#1a1d2e", fontSize: "11px" }}
                itemStyle={{ color: "#1a1d2e", fontSize: "11px" }}
                labelStyle={{ color: "#1a1d2e", fontWeight: 600, fontSize: "11px", wordBreak: "break-word", whiteSpace: "normal" }}
                formatter={(value: number, name: string) => [value, name]}
              />
              <Bar dataKey="avg" name="Avg kWh/100km" radius={[0, 4, 4, 0]}>
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={getBarColor(entry.score)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Route details table */}
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-iv-border">
                <th className="text-left text-iv-text-muted p-2">Route</th>
                <th className="text-center text-iv-text-muted p-2">Trips</th>
                <th className="text-center text-iv-text-muted p-2">Distance</th>
                <th className="text-center text-iv-text-muted p-2">Avg kWh/100km</th>
                <th className="text-center text-iv-text-muted p-2">Range</th>
                <th className="text-center text-iv-text-muted p-2">Score</th>
              </tr>
            </thead>
            <tbody>
              {data.routes.map((route) => (
                <tr key={route.route_key} className="border-t border-iv-border/50 hover:bg-iv-surface/30 transition-colors">
                  <td className="p-2 text-iv-text">
                    <span className="text-iv-cyan">{route.start_location.split(",")[0]}</span>
                    {" → "}
                    <span className="text-iv-cyan">{route.end_location.split(",")[0]}</span>
                  </td>
                  <td className="p-2 text-center text-iv-text">{route.trip_count}</td>
                  <td className="p-2 text-center text-iv-text">{route.total_distance_km} km</td>
                  <td className="p-2 text-center">
                    <span className="font-bold" style={{ color: getBarColor(route.efficiency_score) }}>
                      {route.avg_kwh_100km}
                    </span>
                  </td>
                  <td className="p-2 text-center text-iv-text-muted">
                    {route.min_kwh_100km} – {route.max_kwh_100km}
                  </td>
                  <td className="p-2 text-center">
                    <span
                      className="inline-block px-2 py-0.5 rounded text-xs font-bold"
                      style={{ backgroundColor: getBarColor(route.efficiency_score) + "22", color: getBarColor(route.efficiency_score) }}
                    >
                      {route.efficiency_score}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}