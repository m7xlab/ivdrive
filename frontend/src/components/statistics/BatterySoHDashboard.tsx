"use client";

import React, { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, LineChart, Line, ReferenceLine, Cell } from "recharts";
import { api } from '../../lib/api';
import { TimelineRange } from "./StatisticsShell";

interface MethodResult {
  method: string;
  soh_pct: number | null;
  estimated_kwh: number | null;
  sample_count: number;
  confidence: string;
  inputs: Record<string, any>;
  extra: Record<string, any>;
}

interface BatteryHealthAnalytics {
  user_vehicle_id: string;
  soh_pct: number | null;
  confidence: string;
  estimated_kwh: number | null;
  computed_at: string;
  cached: boolean;
  methods: MethodResult[];
  anomalies: string[];
}

const METHOD_LABELS: Record<string, { name: string; icon: string; blurb: string }> = {
  tesla_capacity: { name: "Tesla Capacity", icon: "🔋", blurb: "est_kwh = median(charging.energy_kwh / delta_soc)" },
  charging_curve_taper: { name: "Charging Taper", icon: "⚡", blurb: "DC power at same SOC over time" },
  cell_imbalance: { name: "Cell Imbalance", icon: "📊", blurb: "Monthly imbalance_mv trend" },
  throughput: { name: "Throughput", icon: "📈", blurb: "Total kWh throughput vs expected" },
  range_drift_over_time: { name: "Range vs New", icon: "🛣️", blurb: "First half vs second half of lookback" },
  fleet_benchmark: { name: "Fleet Benchmark", icon: "🏁", blurb: "Similar-age fleet average (model_year peer)" },
};

const CONFIDENCE_COLORS: Record<string, { ring: string; badge: string }> = {
  high:   { ring: "border-green-500/40 bg-green-500/5",   badge: "bg-green-500/20 text-green-400" },
  medium: { ring: "border-yellow-500/40 bg-yellow-500/5", badge: "bg-yellow-500/20 text-yellow-400" },
  low:    { ring: "border-red-500/40 bg-red-500/5",       badge: "bg-red-500/20 text-red-400" },
};

const TOOLTIP_STYLE = {
  backgroundColor: "var(--iv-charcoal)",
  border: "1px solid var(--iv-border)",
  borderRadius: "8px",
  color: "var(--iv-text)",
};

export function BatterySoHDashboard({
  vehicleId,
  dateRange,
}: {
  vehicleId: string;
  dateRange?: TimelineRange;
}) {
  const [data, setData] = useState<BatteryHealthAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function fetchAnalytics() {
      try {
        setLoading(true);
        setError(null);
        const result = await api.get<BatteryHealthAnalytics>(
          `/api/v1/vehicles/${vehicleId}/battery-health-analytics`
        );
        if (!cancelled) setData(result);
      } catch (err: any) {
        if (!cancelled) setError(err.message || 'Failed to load battery health analytics');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchAnalytics();
    return () => { cancelled = true; };
  }, [vehicleId]);

  if (loading) {
    return (
      <div className="p-4 text-center text-iv-muted">Loading battery health analytics…</div>
    );
  }
  if (error) {
    return <div className="p-4 text-red-500 text-center">{error}</div>;
  }
  if (!data) {
    return <div className="p-4 text-center text-iv-muted">No data available</div>;
  }

  const methodByName = (name: string) => data.methods.find(m => m.method === name);
  const tesla = methodByName('tesla_capacity');
  const taper = methodByName('charging_curve_taper');
  const cellImb = methodByName('cell_imbalance');
  const throughput = methodByName('throughput');
  const rangeDrift = methodByName('range_drift_over_time');
  const fleet = methodByName('fleet_benchmark');

  const forecast = computeForecast(data.soh_pct);
  const taperChartData = taper?.extra?.bucket_changes_pct
    ? buildTaperChartData(taper.extra.bucket_changes_pct)
    : [];
  const imbalanceMonthly = (cellImb?.extra?.monthly_data as Array<{ month: string; median_mv: number }>) || [];
  const imbalanceValue = cellImb?.extra?.median_imbalance_mv as number | undefined;

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <div className="text-xl font-semibold text-iv-text">Battery State of Health</div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-iv-muted">Combined confidence:</span>
          <ConfidenceBadge confidence={data.confidence} />
        </div>
      </div>

      {/* Top 3 cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-iv-border bg-iv-surface p-5">
          <div className="text-xs font-medium text-iv-text-muted uppercase tracking-wider mb-1">
            Calculated SoH
          </div>
          <div className="text-3xl font-bold text-iv-text">
            {data.soh_pct != null ? `${data.soh_pct}%` : '—'}
          </div>
          <div className="text-xs text-iv-muted mt-1">
            {data.cached ? 'cached' : 'freshly computed'}
          </div>
        </div>

        <div className="rounded-xl border border-iv-border bg-iv-surface p-5">
          <div className="text-xs font-medium text-iv-text-muted uppercase tracking-wider mb-1">
            Estimated Capacity
          </div>
          <div className="text-3xl font-bold text-iv-text">
            {data.estimated_kwh != null ? `${data.estimated_kwh} kWh` : '—'}
          </div>
          <div className="text-xs text-iv-muted mt-1">Tesla method median</div>
        </div>

        <div className="rounded-xl border border-iv-border bg-iv-surface p-5">
          <div className="text-xs font-medium text-iv-text-muted uppercase tracking-wider mb-1">
            Skoda BMS SoH
          </div>
          <div className="text-3xl font-bold text-iv-muted">N/A</div>
          <div className="text-xs text-iv-muted mt-1">
            Skoda API doesn't expose this field
          </div>
        </div>
      </div>

      {/* ⚡ Charging Power by SOC */}
      {taperChartData.length > 0 && (
        <div className="rounded-xl border border-iv-border bg-iv-surface p-5">
          <div className="flex items-baseline justify-between mb-1">
            <div className="text-sm font-semibold text-iv-text">⚡ Charging Power by SOC</div>
            {taper?.soh_pct != null && (
              <div className="text-xs text-iv-muted">
                Taper SoH: <span className="font-bold text-iv-text">{taper.soh_pct}%</span>
                {' · '}
                {taper.sample_count} DC samples
              </div>
            )}
          </div>
          <div className="text-xs text-iv-muted mb-4">DC power at each SOC bucket — earlier vs recent</div>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={taperChartData} barGap={2}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey="bucket" stroke="#6b7280" fontSize={12} />
              <YAxis stroke="#6b7280" fontSize={12} unit=" kW" />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="earlier" name="Earlier" fill="#475569" />
              <Bar dataKey="recent" name="Recent" fill="#3b82f6" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 🎯 Per-Method Scorecard */}
      <div className="rounded-xl border border-iv-border bg-iv-surface p-5">
        <div className="text-sm font-semibold text-iv-text mb-1">
          🎯 Per-Method Scorecard
        </div>
        <div className="text-xs text-iv-muted mb-4">
          Why your battery is {data.soh_pct ?? '—'}% — not a black box
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {data.methods
            .filter(m => m.method !== 'combined')
            .map(m => {
              const meta = METHOD_LABELS[m.method] || {
                name: m.method,
                icon: '•',
                blurb: '',
              };
              const colors = CONFIDENCE_COLORS[m.confidence] || CONFIDENCE_COLORS.low;
              return (
                <div
                  key={m.method}
                  className={`rounded-lg border ${colors.ring} p-3`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="text-xs text-iv-muted flex items-center gap-1">
                      <span>{meta.icon}</span>
                      <span>{meta.name}</span>
                    </div>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full uppercase tracking-wide ${colors.badge}`}>
                      {m.confidence}
                    </span>
                  </div>
                  <div className="text-xl font-bold text-iv-text">
                    {m.soh_pct != null ? `${m.soh_pct}%` : '—'}
                  </div>
                  <div className="text-xs text-iv-muted mt-1">
                    {m.sample_count} samples
                  </div>
                </div>
              );
            })}
        </div>
      </div>

      {/* 📊 Cell Imbalance Gauge */}
      {imbalanceValue !== undefined && (
        <div className="rounded-xl border border-iv-border bg-iv-surface p-5">
          <div className="text-sm font-semibold text-iv-text mb-1">
            📊 Cell Imbalance Gauge
          </div>
          <div className="text-xs text-iv-muted mb-4">
            Early warning signal for actual cell defects
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
            <div>
              <div className="text-3xl font-bold text-iv-text">
                {imbalanceValue.toFixed(1)} mV
              </div>
              <div className={`text-xs mt-1 ${imbalanceValue < 15 ? 'text-green-400' : imbalanceValue < 25 ? 'text-yellow-400' : 'text-red-400'}`}>
                {imbalanceValue < 15 ? '✓ Healthy' : imbalanceValue < 25 ? '⚠ Watch' : '⚠ Warning'}
              </div>
            </div>
            {imbalanceMonthly.length > 0 && (
              <ResponsiveContainer width="100%" height={80}>
                <LineChart data={imbalanceMonthly}>
                  <XAxis dataKey="month" hide />
                  <YAxis hide domain={[0, 'dataMax + 5']} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Line
                    type="monotone"
                    dataKey="median_mv"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={{ r: 2, fill: "#3b82f6" }}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      )}

      {/* 🛣️ Range vs New */}
      {rangeDrift?.extra && (
        <div className="rounded-xl border border-iv-border bg-iv-surface p-5">
          <div className="text-sm font-semibold text-iv-text mb-1">
            🛣️ Range vs New
          </div>
          <div className="text-xs text-iv-muted mb-4">
            The single number you actually care about — "how far can I really go?"
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <div className="text-2xl font-bold text-iv-text">
                {rangeDrift.extra.first_half_median_km?.toFixed(0) ?? '—'} km
              </div>
              <div className="text-xs text-iv-muted mt-1">Earlier half median</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-iv-text">
                {rangeDrift.extra.second_half_median_km?.toFixed(0) ?? '—'} km
              </div>
              <div className="text-xs text-iv-muted mt-1">Recent half median</div>
            </div>
            <div>
              <div className={`text-2xl font-bold ${(rangeDrift.extra.retention_pct ?? 0) >= 90 ? 'text-green-400' : (rangeDrift.extra.retention_pct ?? 0) >= 70 ? 'text-yellow-400' : 'text-red-400'}`}>
                {rangeDrift.extra.retention_pct?.toFixed(1) ?? '—'}%
              </div>
              <div className="text-xs text-iv-muted mt-1">Retention</div>
            </div>
          </div>
        </div>
      )}

      {/* 🏁 Fleet Benchmark */}
      {fleet?.extra && (
        <div className="rounded-xl border border-iv-border bg-iv-surface p-5">
          <div className="text-sm font-semibold text-iv-text mb-1">
            🏁 Fleet Benchmark
          </div>
          <div className="text-xs text-iv-muted mb-4">
            Are you above or below average for your car's age?
          </div>
          <div className="flex items-baseline gap-4 flex-wrap">
            <div>
              <div className="text-3xl font-bold text-iv-text">
                {fleet.soh_pct?.toFixed(1) ?? '—'}%
              </div>
              <div className="text-xs text-iv-muted mt-1">Your battery</div>
            </div>
            <div className="text-iv-muted">vs</div>
            <div>
              <div className="text-3xl font-bold text-iv-muted">
                {fleet.extra.similar_age_avg_soh?.toFixed(1) ?? '—'}%
              </div>
              <div className="text-xs text-iv-muted mt-1">
                Similar-age fleet avg ({fleet.extra.peer_count ?? 0} peers)
              </div>
            </div>
            {fleet.soh_pct != null && fleet.extra.similar_age_avg_soh != null && (
              <div className="ml-auto">
                <span className={`text-xs px-2 py-1 rounded-full ${
                  fleet.soh_pct > fleet.extra.similar_age_avg_soh
                    ? 'bg-green-500/20 text-green-400'
                    : fleet.soh_pct < fleet.extra.similar_age_avg_soh
                    ? 'bg-red-500/20 text-red-400'
                    : 'bg-gray-500/20 text-gray-400'
                }`}>
                  {fleet.soh_pct > fleet.extra.similar_age_avg_soh ? '↑ above average' :
                   fleet.soh_pct < fleet.extra.similar_age_avg_soh ? '↓ below average' :
                   '= at average'}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 📈 Forecast strip */}
      {forecast && (
        <div className="rounded-xl border border-iv-border bg-iv-surface p-5">
          <div className="text-sm font-semibold text-iv-text mb-1">
            📈 Forecast
          </div>
          <div className="text-xs text-iv-muted mb-3">
            Based on Skoda Enyaq fleet average (~1.8% degradation/year)
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <div className="text-2xl font-bold text-iv-text">{forecast.oneYear}%</div>
              <div className="text-xs text-iv-muted mt-1">1 year</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-iv-text">{forecast.threeYear}%</div>
              <div className="text-xs text-iv-muted mt-1">3 years</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-iv-text">{forecast.fiveYear}%</div>
              <div className="text-xs text-iv-muted mt-1">5 years</div>
            </div>
          </div>
        </div>
      )}

      {/* Anomalies */}
      {data.anomalies.length > 0 && (
        <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/5 p-4">
          <div className="text-sm font-semibold text-yellow-400 mb-2">⚠️ Anomalies</div>
          <ul className="text-xs text-iv-muted space-y-1">
            {data.anomalies.map((a, i) => (
              <li key={i}>• {a}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function buildTaperChartData(
  bucketChanges: Record<string, { earlier_median_kw: number; recent_median_kw: number }>
): Array<{ bucket: string; earlier: number; recent: number }> {
  return Object.entries(bucketChanges).map(([bucket, d]) => ({
    bucket: `${bucket}%`,
    earlier: d.earlier_median_kw,
    recent: d.recent_median_kw,
  }));
}

function computeForecast(currentSoh: number | null) {
  if (currentSoh == null) return null;
  const annualDeg = 1.8; // Skoda Enyaq fleet average per research doc
  return {
    oneYear: Math.max(0, currentSoh - annualDeg).toFixed(1),
    threeYear: Math.max(0, currentSoh - annualDeg * 3).toFixed(1),
    fiveYear: Math.max(0, currentSoh - annualDeg * 5).toFixed(1),
  };
}

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const colors = CONFIDENCE_COLORS[confidence] || CONFIDENCE_COLORS.low;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full uppercase tracking-wide ${colors.badge}`}>
      {confidence}
    </span>
  );
}
