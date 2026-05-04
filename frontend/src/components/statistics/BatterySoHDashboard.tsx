"use client";

import React, { useEffect, useState } from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { statisticsApi } from '../../lib/api/statistics';

interface SoHData {
  factory_capacity_kwh: number | null;
  skoda_soh_pct: number | null;
  calculated_soh_pct: number | null;
  estimated_capacity_kwh: number | null;
  curve: Array<{
    date: string;
    capacity_kwh: number;
    soh_pct: number;
  }>;
  sample_count: number;
}

export function BatterySoHDashboard({ vehicleId }: { vehicleId: string }) {
  const [data, setData] = useState<SoHData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchSoH() {
      try {
        setLoading(true);
        const result = await statisticsApi.getBatterySoH(vehicleId);
        setData({
          factory_capacity_kwh: result.factory_capacity_kwh,
          skoda_soh_pct: result.skoda_soh_pct,
          calculated_soh_pct: result.derived_soh_pct,
          estimated_capacity_kwh: result.derived_capacity_kwh,
          curve: result.curve.map(c => ({ date: c.date || c.month, capacity_kwh: c.capacity_kwh || c.estimated_kwh, soh_pct: c.soh_pct })),
          sample_count: result.total_soh_estimates,
        });
      } catch (err: any) {
        setError(err.message || 'Failed to load battery SoH data');
      } finally {
        setLoading(false);
      }
    }
    fetchSoH();
  }, [vehicleId]);

  if (loading) return <div className="p-4 text-center text-iv-muted">Loading battery health analysis...</div>;
  if (error) return <div className="p-4 text-red-500 text-center">{error}</div>;
  if (!data) return <div className="p-4 text-center">No data available</div>;

  const chartData = data.curve.map(p => {
    const dateObj = p.date.length === 7 ? new Date(`${p.date}-01`) : new Date(p.date);
    return {
      date: dateObj.toLocaleDateString(undefined, { month: 'short', year: 'numeric' }),
      "SoH %": p.soh_pct != null ? parseFloat(p.soh_pct.toFixed(1)) : null,
      "Capacity (kWh)": p.capacity_kwh != null ? parseFloat(p.capacity_kwh.toFixed(2)) : null,
    };
  });

  return (
    <div className="space-y-6">
      <div className="text-xl font-semibold text-iv-text">Battery State of Health (SoH)</div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-iv-border bg-iv-surface p-5">
          <div className="text-xs font-medium text-iv-text-muted uppercase tracking-wider mb-1">Calculated SoH</div>
          <div className="text-3xl font-bold text-iv-text">
            {data.calculated_soh_pct ? `${data.calculated_soh_pct}%` : 'N/A'}
          </div>
          <div className="text-xs text-iv-muted mt-1">Based on {data.sample_count} charging sessions</div>
        </div>

        <div className="rounded-xl border border-iv-border bg-iv-surface p-5">
          <div className="text-xs font-medium text-iv-text-muted uppercase tracking-wider mb-1">Estimated Capacity</div>
          <div className="text-3xl font-bold text-iv-text">
            {data.estimated_capacity_kwh ? `${data.estimated_capacity_kwh} kWh` : 'N/A'}
          </div>
          <div className="text-xs text-iv-muted mt-1">Factory: {data.factory_capacity_kwh} kWh</div>
        </div>

        <div className="rounded-xl border border-iv-border bg-iv-surface p-5">
          <div className="text-xs font-medium text-iv-text-muted uppercase tracking-wider mb-1">Skoda BMS SoH</div>
          <div className="text-3xl font-bold text-iv-text">
            {data.skoda_soh_pct ? `${data.skoda_soh_pct}%` : 'N/A'}
          </div>
          <div className="text-xs text-iv-muted mt-1">Official reported value</div>
        </div>
      </div>

      <div className="rounded-xl border border-iv-border bg-iv-surface p-5">
        <div className="text-sm font-semibold text-iv-text mb-1">Degradation Curve</div>
        <div className="text-xs text-iv-muted mb-4">Capacity and SoH estimates over time</div>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis dataKey="date" stroke="#6b7280" fontSize={12} />
            <YAxis stroke="#6b7280" fontSize={12} yAxisId="left" domain={[0, 110]} tickFormatter={v => `${v}%`} />
            <YAxis stroke="#6b7280" fontSize={12} yAxisId="right" orientation="right" domain={[0, 100]} tickFormatter={v => `${v} kWh`} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #2d2d44', borderRadius: '8px', color: '#e5e7eb' }}
              labelStyle={{ color: '#9ca3af' }}
              formatter={(value: any, name: string) => [name === "SoH %" ? `${value}%` : `${value} kWh`, name]}
            />
            <Area type="monotone" dataKey="SoH %" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.2} yAxisId="left" />
            <Area type="monotone" dataKey="Capacity (kWh)" stroke="#10b981" fill="#10b981" fillOpacity={0.2} yAxisId="right" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
