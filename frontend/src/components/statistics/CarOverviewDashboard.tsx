"use client";

import React, { useEffect, useState, useCallback } from "react";
import { format } from "date-fns";
import {
  Wifi,
  Wind,
  Zap,
  Car,
  Activity,
  Gauge,
  TrendingUp,
  BarChart3,
} from "lucide-react";
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceArea,
  ReferenceLine,
  CartesianGrid,
  ComposedChart,
} from "recharts";
import { api } from "@/lib/api";
import { Battery, Zap as ZapIcon, Maximize } from "lucide-react";
import { cn } from "@/lib/cn";
import type { TimelineRange } from "./StatisticsShell";

export type StateToggleId = "online" | "climatization" | "charging" | "driving";

export type SectionId = "levels" | "consumption" | "efficiency" | "chargingPower";

export interface StateBand {
  from_date: string;
  to_date: string;
  state: string;
}

const STATE_TOGGLES: { id: StateToggleId; label: string; icon: React.ElementType }[] = [
  { id: "online", label: "Online", icon: Wifi },
  { id: "climatization", label: "Climatization", icon: Wind },
  { id: "charging", label: "Charging", icon: Zap },
  { id: "driving", label: "Driving", icon: Car },
];

const STATE_COLORS: Record<string, string> = {
  online: "rgba(74, 168, 46, 0.2)",
  climatization: "rgba(255, 193, 7, 0.2)",
  charging: "rgba(0, 212, 255, 0.2)",
  driving: "rgba(139, 92, 246, 0.2)",
};

const STORAGE_KEY = "ivdrive-car-overview-state-toggles";

function loadGlobalToggles(): Record<StateToggleId, boolean> {
  if (typeof window === "undefined") return { online: false, climatization: false, charging: false, driving: false };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { online: false, climatization: false, charging: false, driving: false };
    const parsed = JSON.parse(raw) as Record<string, boolean>;
    return {
      online: Boolean(parsed.online),
      climatization: Boolean(parsed.climatization),
      charging: Boolean(parsed.charging),
      driving: Boolean(parsed.driving),
    };
  } catch (err) {
      console.error('CarOverview Fetch Error:', err);
    return { online: false, climatization: false, charging: false, driving: false };
  }
}

function saveGlobalToggles(toggles: Record<StateToggleId, boolean>) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toggles));
  } catch (err) {
      console.error('CarOverview Fetch Error:', err);
    /* ignore */
  }
}

interface BatteryPoint {
  timestamp: string;
  level: number;
}
interface RangePoint {
  timestamp: string;
  range_km: number;
}
interface ChargingPoint {
  first_date: string;
  last_date: string;
  charge_power_kw: number | null;
  charge_rate_km_per_hour: number | null;
}

export interface CarOverviewDashboardProps {
  vehicleId: string;
  dateRange: TimelineRange;
  /** Optional period stats for summary section */
  stats?: Array<{
    period: string;
    drives_count: number;
    total_distance_km: number;
    charging_sessions_count: number;
    total_energy_kwh: number;
    avg_energy_per_session_kwh: number;
  }>;
}

function toISO(d: Date) {
  return d.toISOString();
}


function StatTable({ data, dataKeys }: { data: any[], dataKeys: { key: string, label: string, color: string, unit: string, decimals?: number }[] }) {
  if (!data || data.length === 0) return null;
  return (
    <div className="w-full mt-4 bg-iv-charcoal/50 rounded border border-iv-border text-[11px] font-mono">
      <div className="hidden sm:grid grid-cols-6 border-b border-iv-border/50 py-1.5 px-3 text-iv-cyan font-semibold">
        <div className="col-span-2">Name</div>
        <div className="text-right">Mean</div>
        <div className="text-right">Last *</div>
        <div className="text-right">Max</div>
        <div className="text-right">Min</div>
      </div>
      {dataKeys.map(({key, label, color, unit, decimals = 1}) => {
         const valid = data.filter(d => d[key] != null).map(d => Number(d[key]));
         if (valid.length === 0) return null;
         const mean = valid.reduce((a,b)=>a+b,0)/valid.length;
         const last = valid[valid.length-1];
         const max = Math.max(...valid);
         const min = Math.min(...valid);
         return (
           <React.Fragment key={key}>
             {/* Desktop: Grid Row */}
             <div className="hidden sm:grid grid-cols-6 py-1.5 px-3 hover:bg-iv-surface/50 border-b border-iv-border/20 last:border-0 items-center">
               <div className="col-span-2 flex items-center gap-2">
                 <div className="w-2.5 h-1 rounded-full" style={{ backgroundColor: color }} />
                 <span className="text-iv-text font-sans text-xs font-medium truncate">{label}</span>
               </div>
               <div className="text-right text-iv-muted">{mean.toFixed(decimals)} {unit}</div>
               <div className="text-right text-iv-muted">{last.toFixed(decimals)} {unit}</div>
               <div className="text-right text-iv-muted">{max.toFixed(decimals)} {unit}</div>
               <div className="text-right text-iv-muted">{min.toFixed(decimals)} {unit}</div>
             </div>
             
             {/* Mobile: Stacked Row */}
             <div className="sm:hidden flex flex-col gap-1 p-3 border-b border-iv-border/20 last:border-0">
               <div className="flex items-center gap-2 mb-1">
                 <div className="w-2.5 h-1 rounded-full" style={{ backgroundColor: color }} />
                 <span className="text-iv-text font-sans text-xs font-bold">{label}</span>
               </div>
               <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                 <div className="flex justify-between">
                   <span className="text-iv-muted uppercase text-[9px]">Mean:</span>
                   <span className="text-iv-text">{mean.toFixed(decimals)} {unit}</span>
                 </div>
                 <div className="flex justify-between">
                   <span className="text-iv-muted uppercase text-[9px]">Last:</span>
                   <span className="text-iv-text">{last.toFixed(decimals)} {unit}</span>
                 </div>
                 <div className="flex justify-between">
                   <span className="text-iv-muted uppercase text-[9px]">Max:</span>
                   <span className="text-iv-text">{max.toFixed(decimals)} {unit}</span>
                 </div>
                 <div className="flex justify-between">
                   <span className="text-iv-muted uppercase text-[9px]">Min:</span>
                   <span className="text-iv-text">{min.toFixed(decimals)} {unit}</span>
                 </div>
               </div>
             </div>
           </React.Fragment>
         );
      })}
    </div>
  );
}

export function CarOverviewDashboard({

  vehicleId,
  dateRange,
  stats = [],
}: CarOverviewDashboardProps) {
  const [globalToggles, setGlobalToggles] = useState<Record<StateToggleId, boolean>>(() => loadGlobalToggles());
  const [battery, setBattery] = useState<BatteryPoint[]>([]);
  const [range, setRange] = useState<RangePoint[]>([]);
  const [charging, setCharging] = useState<ChargingPoint[]>([]);
  const [stateBands, setStateBands] = useState<StateBand[]>([]);
  const [electricConsumption, setElectricConsumption] = useState<Array<{ time: string; consumption: number }>>([]);
  const [rangeAt100, setRangeAt100] = useState<Array<{ time: string; range_estimated_full: number }>>([]);
  const [wltpKm, setWltpKm] = useState<number | null>(null);
  const [efficiencyData, setEfficiencyData] = useState<Array<{ time: string; efficiency_pct: number }>>([]);
  const [loading, setLoading] = useState(true);

  const fromISO = toISO(dateRange.from);
  const toISOVal = toISO(dateRange.to);

  const [levelsStep, setLevelsStep] = useState<Array<{ timestamp: string; level: number }>>([]);
  const [rangesStep, setRangesStep] = useState<Array<{ timestamp: string; range_km: number }>>([]);
  const [batteryTemp, setBatteryTemp] = useState<Array<{ time: string; battery_temperature: number }>>([]);
  const [outsideTemp, setOutsideTemp] = useState<Array<{ time: string; outside_temp_celsius: number }>>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [b, r, c, bands, range100, wltp, eff, lStep, rStep, oTemp, bTemp, elecCons] = await Promise.all([
        api.getBatteryHistory(vehicleId, 10000, fromISO, toISOVal),
        api.getRangeHistory(vehicleId, 10000, fromISO, toISOVal),
        api.getChargingHistory(vehicleId, 10000, fromISO, toISOVal),
        api.getOverviewStateBands(vehicleId, {
          fromDate: fromISO,
          toDate: toISOVal,
          limit: 10000,
        }),
        api.getOverviewRangeAt100(vehicleId, {
          fromDate: fromISO,
          toDate: toISOVal,
          limit: 10000,
        }),
        api.getOverviewWltp(vehicleId),
        api.getOverviewEfficiency(vehicleId, {
          fromDate: fromISO,
          toDate: toISOVal,
          limit: 10000,
        }),
        api.getLevelsStep(vehicleId, 10000, fromISO, toISOVal),
        api.getRangesStep(vehicleId, 10000, fromISO, toISOVal),
        api.getOutsideTemperature(vehicleId, 10000, fromISO, toISOVal),
        api.getBatteryTemperature(vehicleId, 10000, fromISO, toISOVal),
        api.getElectricConsumption(vehicleId, 10000, fromISO, toISOVal),
      ]);
      setBattery(b ?? []);
      setRange(r ?? []);
      setCharging(c ?? []);
      setStateBands(bands ?? []);
      setRangeAt100(range100 ?? []);
      setElectricConsumption(elecCons ?? []);
      setWltpKm(wltp?.wltp_range_km ?? null);
      setEfficiencyData(eff ?? []);
      setLevelsStep(lStep ?? []);
      setRangesStep(rStep ?? []);
      setOutsideTemp(oTemp ?? []);
      setBatteryTemp(bTemp ?? []);
    } catch (err) {
      console.error('CarOverview Fetch Error:', err);
      setBattery([]);
      setRange([]);
      setCharging([]);
      setStateBands([]);
      setRangeAt100([]);
      setElectricConsumption([]);
      setWltpKm(null);
      setEfficiencyData([]);
      setLevelsStep([]);
      setRangesStep([]);
      setOutsideTemp([]);
      setBatteryTemp([]);
    } finally {
      setLoading(false);
    }
  }, [vehicleId, fromISO, toISOVal]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const toggle = (id: StateToggleId) => {
    setGlobalToggles((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      saveGlobalToggles(next);
      return next;
    });
  };

  const hasAnyData = battery.length > 0 || range.length > 0 || charging.length > 0 || stateBands.length > 0;

  if (loading && !hasAnyData) {
    return (
      <div className="glass rounded-xl p-12 flex flex-col items-center justify-center gap-3">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-iv-border border-t-iv-green" />
        <p className="text-sm text-iv-muted">Loading Car Overview...</p>
      </div>
    );
  }

  if (!hasAnyData) {
    return (
      <div className="glass rounded-xl p-12 text-center">
        <Activity size={32} className="mx-auto mb-3 text-iv-muted" />
        <p className="text-sm text-iv-muted">No telemetry data for this period yet.</p>
        <p className="text-xs text-iv-muted mt-1">Data appears as the collector syncs your vehicle.</p>
      </div>
    );
  }

  // Levels & Range: prefer step-style (first_date + last_date per segment) when available; else merge battery + range.
  const timeSet = new Set<string>();
  const useStep = levelsStep.length > 0 || rangesStep.length > 0;
  if (useStep) {
    levelsStep.forEach((p) => timeSet.add(p.timestamp));
    rangesStep.forEach((p) => timeSet.add(p.timestamp));
  } else {
    battery.forEach((p) => timeSet.add(p.timestamp));
    range.forEach((p) => timeSet.add(p.timestamp));
  }
  outsideTemp.forEach((p) => timeSet.add(p.time));
  batteryTemp.forEach((p) => timeSet.add(p.time));
  const levelsRangeData = Array.from(timeSet).filter(Boolean)
    .sort()
    .map((ts) => {
      const timeMs = new Date(ts).getTime();
      const level = useStep
        ? (levelsStep.find((x) => x.timestamp === ts)?.level ?? battery.find((x) => x.timestamp === ts)?.level ?? null)
        : (battery.find((x) => x.timestamp === ts)?.level ?? null);
      const range_km = useStep
        ? (rangesStep.find((x) => x.timestamp === ts)?.range_km ?? range.find((x) => x.timestamp === ts)?.range_km ?? null)
        : (range.find((x) => x.timestamp === ts)?.range_km ?? null);
      const ot = outsideTemp.find((x) => x.time && ts && (x.time === ts || String(x.time).slice(0, 19) === String(ts).slice(0, 19)));
      const bt = batteryTemp.find((x) => x.time && ts && (x.time === ts || String(x.time).slice(0, 19) === String(ts).slice(0, 19)));
      const out: { time: string; timeMs: number; label: string; level: number | null; range_km: number | null; outside_temp?: number } = {
        time: ts,
        timeMs,
        label: format(new Date(ts), "d MMM HH:mm"),
        level,
        range_km,
      };
      if (ot) out.outside_temp = ot.outside_temp_celsius;
      if (bt) out.battery_temp = bt.battery_temperature;
      return out;
    })
    .filter((d) => d.level != null || d.range_km != null || d.outside_temp != null || d.battery_temp != null);

  // Avg km/% (range/level) trend for Levels & Range caption
  const kmPerPctSamples = levelsRangeData.filter((d) => d.level != null && d.level > 0 && d.range_km != null);
  const avgKmPerPct =
    kmPerPctSamples.length > 0
      ? kmPerPctSamples.reduce((sum, d) => sum + (d.range_km ?? 0) / (d.level ?? 1), 0) / kmPerPctSamples.length
      : null;

  // Charging chart: points from charging states. Use timeMs for X so ReferenceArea works.
  const timeSetCharging = new Set<string>();
  charging.forEach((c) => {
    timeSetCharging.add(c.first_date);
    if (c.last_date) timeSetCharging.add(c.last_date);
  });
  outsideTemp.forEach((p) => timeSetCharging.add(p.time));
  batteryTemp.forEach((p) => timeSetCharging.add(p.time));

  const chargingChartData = Array.from(timeSetCharging).filter(Boolean).map((ts) => {
    const timeMs = new Date(ts).getTime();
    // Find nearest charging point that wraps this timeMs
    const c = charging.find(x => {
        const from = new Date(x.first_date).getTime();
        const to = new Date(x.last_date || x.first_date).getTime();
        return timeMs >= from && timeMs <= to;
    });
    const ot = outsideTemp.find((x) => x.time && ts && (x.time === ts || String(x.time).slice(0, 19) === String(ts).slice(0, 19)));
    const bt = batteryTemp.find((x) => x.time && ts && (x.time === ts || String(x.time).slice(0, 19) === String(ts).slice(0, 19)));
    return {
      time: ts,
      timeMs,
      label: format(new Date(ts), "d MMM HH:mm"),
      power: c?.charge_power_kw ?? null,
      rate: c?.charge_rate_km_per_hour ?? null,
      outside_temp: ot?.outside_temp_celsius ?? null,
      battery_temp: bt?.battery_temperature ?? null,
    };
  }).filter((d) => d.power != null || d.rate != null || d.outside_temp != null || d.battery_temp != null).sort((a, b) => a.timeMs - b.timeMs);

  // Global state bands: one set of toggles applies to all charts (overlay visibility only)
  const visibleBands = stateBands.filter((b) => globalToggles[b.state as StateToggleId]);
  const bandTimestamps = visibleBands
    .map((b) => {
      const fromMs = new Date(b.from_date).getTime();
      const toMs = new Date(b.to_date).getTime();
      if (!Number.isFinite(fromMs) || !Number.isFinite(toMs)) return null;
      return { ...b, fromMs, toMs };
    })
    .filter((x): x is NonNullable<typeof x> => x != null);

  const rangeFromMs = dateRange.from.getTime();
  const rangeToMs = dateRange.to.getTime();

  // Adaptive time domain: fit to data + bands with padding so chart is granular (no empty half)
  const PADDING_MS = 5 * 60 * 1000; // 5 min
  const paddingRatio = 0.02; // 2% on each side
  function adaptiveTimeDomain(
    dataTimes: number[],
    bandTimes: { fromMs: number; toMs: number }[],
    fallback: [number, number]
  ): [number, number] {
    const all = [
      ...dataTimes,
      ...bandTimes.flatMap((b) => [b.fromMs, b.toMs]),
    ].filter(Number.isFinite);
    if (all.length === 0) return fallback;
    const lo = Math.min(...all);
    const hi = Math.max(...all);
    const span = hi - lo || 1;
    const pad = Math.max(PADDING_MS, span * paddingRatio);
    return [lo - pad, hi + pad];
  }

  // Range at 100% + WLTP chart (Grafana-style)
  const timeSetCons = new Set<string>();
  rangeAt100.forEach((p) => timeSetCons.add(p.time));
  electricConsumption.forEach((p) => timeSetCons.add(p.time));
  
  const rangeAt100ChartData = Array.from(timeSetCons).filter(Boolean).map((time) => {
    const r100 = rangeAt100.find(r => r.time && time && (r.time === time || String(r.time).slice(0, 19) === String(time).slice(0, 19)));
    const eCons = electricConsumption.find(e => e.time && time && (e.time === time || String(e.time).slice(0, 19) === String(time).slice(0, 19)));
    return {
      time: time,
      timeMs: new Date(time).getTime(),
      label: format(new Date(time), "d MMM HH:mm"),
      range_estimated_full: r100 ? r100.range_estimated_full : null,
      consumption: eCons ? eCons.consumption : null,
    };
  }).sort((a, b) => a.timeMs - b.timeMs);
  // Efficiency chart (Grafana-style) + 100% reference
  const efficiencyChartData = efficiencyData.map((p) => ({
    time: p.time,
    timeMs: new Date(p.time).getTime(),
    label: format(new Date(p.time), "d MMM HH:mm"),
    efficiency_pct: p.efficiency_pct,
  })).sort((a, b) => a.timeMs - b.timeMs);

  // Adaptive domain: fit to data + state bands so chart fills the space (no empty half)
  const levelsDataTimes = levelsRangeData.map((d) => d.timeMs);
  const levelsDomain: [number, number] = adaptiveTimeDomain(
    levelsDataTimes,
    bandTimestamps,
    [rangeFromMs, rangeToMs]
  );
  const chargingDomain: [number, number] = adaptiveTimeDomain(
    chargingChartData.map((d) => d.timeMs),
    bandTimestamps,
    [rangeFromMs, rangeToMs]
  );
  const rangeAt100Domain: [number, number] = adaptiveTimeDomain(
    rangeAt100ChartData.map((d) => d.timeMs),
    bandTimestamps,
    [rangeFromMs, rangeToMs]
  );
  const efficiencyDomain: [number, number] = adaptiveTimeDomain(
    efficiencyChartData.map((d) => d.timeMs),
    bandTimestamps,
    [rangeFromMs, rangeToMs]
  );

  return (
    <div className="space-y-6">
      {/* Global state toggles: apply to all charts below, persisted across refresh */}
      
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
        <div className="glass rounded-xl p-5 border border-iv-border flex flex-col justify-between">
          <div className="flex items-center gap-2 text-iv-muted mb-2">
            <Battery size={16} className="text-iv-green" />
            <span className="text-sm font-medium">Battery (now)</span>
          </div>
          <div className="flex items-end gap-2">
            <span className="text-3xl font-bold text-iv-text">{battery.length > 0 ? battery[0].level : "--"}</span>
            <span className="text-lg text-iv-muted mb-0.5">%</span>
          </div>
        </div>
        <div className="glass rounded-xl p-5 border border-iv-border flex flex-col justify-between">
          <div className="flex items-center gap-2 text-iv-muted mb-2">
            <Maximize size={16} className="text-iv-cyan" />
            <span className="text-sm font-medium">Projected Electric Range (now)</span>
          </div>
          <div className="flex items-end gap-2">
            <span className="text-3xl font-bold text-iv-text">{range.length > 0 ? Math.round(range[0].range_km) : "--"}</span>
            <span className="text-lg text-iv-muted mb-0.5">km</span>
          </div>
        </div>
        <div className="glass rounded-xl p-5 border border-iv-border flex flex-col justify-between">
          <div className="flex items-center gap-2 text-iv-muted mb-2">
            <ZapIcon size={16} className="text-amber-500" />
            <span className="text-sm font-medium">Charging Power (now)</span>
          </div>
          <div className="flex items-end gap-2">
            <span className="text-3xl font-bold text-iv-text">{charging.length > 0 && charging[charging.length-1].charge_power_kw ? charging[charging.length-1].charge_power_kw : "0"}</span>
            <span className="text-lg text-iv-muted mb-0.5">kW</span>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {STATE_TOGGLES.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => toggle(id)}
            className={cn(
              "inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-all",
              globalToggles[id]
                ? "border-iv-green/50 bg-iv-green/15 text-iv-green"
                : "border-iv-border bg-iv-surface/60 text-iv-muted hover:text-iv-text"
            )}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
        {stateBands.length === 0 && (
          <span className="text-xs text-iv-muted ml-1">No state periods in range.</span>
        )}
      </div>

      {/* 1. Levels & Range */}
      {levelsRangeData.length > 0 && (
        <div className="glass rounded-xl p-5">
          <>
          <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2">
            <Gauge size={14} /> Levels & Range
          </h3>
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={levelsRangeData}
                margin={{ top: 8, right: 8, left: 8, bottom: 8 }}
              >
                <XAxis
                  dataKey="timeMs"
                  type="number"
                  domain={levelsDomain}
                  tickFormatter={(v) => {
                    const span = levelsDomain[1] - levelsDomain[0];
                    return span <= 24 * 60 * 60 * 1000
                      ? format(new Date(v), "HH:mm")
                      : format(new Date(v), "d MMM HH:mm");
                  }}
                  stroke="#8b8fa3"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                />
                <CartesianGrid strokeDasharray="3 3" stroke="var(--iv-border)" opacity={0.5} />
                {/* State bands behind the data so they are visible */}
                {bandTimestamps.map((band, i) => (
                  <ReferenceArea
                    key={`${band.from_date}-${i}`}
                    yAxisId="level"
                    x1={band.fromMs}
                    x2={band.toMs}
                    fill={STATE_COLORS[band.state] ?? "rgba(128,128,128,0.2)"}
                    strokeOpacity={0}
                  />
                ))}
                <YAxis
                  yAxisId="level"
                  orientation="left"
                  stroke="#8b8fa3"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${v}%`}
                  domain={['auto', 'auto']}
                />
                <YAxis
                  yAxisId="range"
                  orientation="right"
                  stroke="#8b8fa3"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${v} km`}
                />
                {levelsRangeData.some((d) => d.outside_temp != null) && (
                  <YAxis
                    yAxisId="temp"
                    orientation="right"
                    stroke="#f59e0b"
                    fontSize={10}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `${v}°C`}
                  />
                )}
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    return (
                      <div className="rounded-lg bg-iv-charcoal border border-iv-border px-3 py-2 shadow-xl">
                        <p className="text-xs text-iv-muted">
                          {label != null ? format(new Date(label as number), "d MMM HH:mm") : ""}
                        </p>
                        {payload.map((p) => (
                          <p key={p.dataKey} className="text-sm font-semibold text-iv-text">
                            {p.name}: {p.value != null ? (p.dataKey === "level" ? `${Number(p.value).toFixed(1)}%` : p.dataKey === "outside_temp" || p.dataKey === "battery_temp" ? `${p.value}°C` : `${Number(p.value).toFixed(0)} km`) : "—"}
                          </p>
                        ))}
                      </div>
                    );
                  }}
                />
                {levelsRangeData.some((d) => d.range_km != null) && (
                  <Area
                    yAxisId="range"
                    type="monotone"
                    dataKey="range_km"
                    name="Range"
                    stroke="#4BA82E"
                    fill="#4BA82E"
                    fillOpacity={0.3}
                    strokeWidth={2}
                    connectNulls
                  />
                )}
                {levelsRangeData.some((d) => d.level != null) && (
                  <Area
                    yAxisId="level"
                    type="monotone"
                    dataKey="level"
                    name="Level %"
                    stroke="#00D4FF"
                    fill="#00D4FF"
                    fillOpacity={0.2}
                    strokeWidth={2}
                    connectNulls
                  />
                )}
                {levelsRangeData.some((d) => d.outside_temp != null) && (
                  <Line
                    yAxisId="temp"
                    type="monotone"
                    dataKey="outside_temp"
                    name="Outside temp"
                    stroke="#f59e0b"
                    strokeWidth={1}
                    dot={{ r: 1, strokeWidth: 1 }}
                    connectNulls
                  />
                )}
              
                {levelsRangeData.some((d) => d.battery_temp != null) && (
                  <Line
                    yAxisId="temp"
                    type="monotone"
                    dataKey="battery_temp"
                    name="Battery temp"
                    stroke="#e11d48"
                    strokeWidth={1}
                    dot={{ r: 1, strokeWidth: 1 }}
                    connectNulls
                  />
                )}
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <StatTable data={levelsRangeData} dataKeys={[
            { key: "level", label: "Level %", color: "#00D4FF", unit: "%", decimals: 0 },
            { key: "range_km", label: "Range", color: "#4BA82E", unit: "km", decimals: 0 },
            { key: "outside_temp", label: "Outside Temperature", color: "#f59e0b", unit: "°C", decimals: 1 },
            { key: "battery_temp", label: "Battery Temperature", color: "#e11d48", unit: "°C", decimals: 1 }
          ]} />
          {(avgKmPerPct != null || useStep) && (
            <p className="text-xs text-iv-muted mt-3">
              {useStep && <span>Step-style (first/last date per segment). </span>}
              {avgKmPerPct != null && (
                <span>Avg km/% (range per SoC): {avgKmPerPct.toFixed(1)} km/% — trend of how range drops with level.</span>
              )}
            </p>
          )}
          </>
        </div>
      )}

      {/* 2. Consumption & Range at 100% SoC (Grafana-style: range at 100% + WLTP reference) */}
      <div className="glass rounded-xl p-5">
        <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2">
          <TrendingUp size={14} /> Consumption & Range extrapolated to 100% SoC
        </h3>
        {rangeAt100ChartData.length > 0 || wltpKm != null ? (
          <>
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={
                  rangeAt100ChartData.length > 0
                    ? rangeAt100ChartData.map((d) => ({
                        ...d,
                        wltp: wltpKm ?? undefined,
                      }))
                    : [
                        { timeMs: rangeFromMs, range_estimated_full: undefined, wltp: wltpKm ?? undefined },
                        { timeMs: rangeToMs, range_estimated_full: undefined, wltp: wltpKm ?? undefined },
                      ]
                }
                margin={{ top: 8, right: 8, left: 8, bottom: 8 }}
              >
                <XAxis
                  dataKey="timeMs"
                  type="number"
                  domain={rangeAt100Domain}
                  tickFormatter={(v) => {
                    const span = rangeAt100Domain[1] - rangeAt100Domain[0];
                    return span <= 24 * 60 * 60 * 1000
                      ? format(new Date(v), "HH:mm")
                      : format(new Date(v), "d MMM");
                  }}
                  stroke="#8b8fa3"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                />
                <CartesianGrid strokeDasharray="3 3" stroke="var(--iv-border)" opacity={0.5} />
                {bandTimestamps.map((band, i) => (
                  <ReferenceArea
                    key={`ra100-${band.from_date}-${i}`}
                    yAxisId="range100"
                    x1={band.fromMs}
                    x2={band.toMs}
                    fill={STATE_COLORS[band.state] ?? "rgba(128,128,128,0.2)"}
                    strokeOpacity={0}
                  />
                ))}
                <YAxis
                  yAxisId="range100"
                  stroke="#8b8fa3"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${v} km`}
                />
                <YAxis
                  yAxisId="cons"
                  orientation="right"
                  stroke="#f59e0b"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${v} kWh`}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    return (
                      <div className="rounded-lg bg-iv-charcoal border border-iv-border px-3 py-2 shadow-xl">
                        <p className="text-xs text-iv-muted">
                          {label != null ? format(new Date(label as number), "d MMM HH:mm") : ""}
                        </p>
                        {payload.map((p) => (
                          <p key={p.dataKey} className="text-sm font-semibold text-iv-text">
                            {p.name}: {p.value != null ? (p.dataKey === "consumption" ? `${Number(p.value).toFixed(1)} kWh/100km` : `${Number(p.value).toFixed(0)} km`) : "—"}
                          </p>
                        ))}
                      </div>
                    );
                  }}
                />
                <Area
                  yAxisId="range100"
                  type="step"
                  dataKey="range_estimated_full"
                  name="Range at 100% primary"
                  stroke="#4BA82E"
                  fill="#4BA82E"
                  fillOpacity={0.2}
                  strokeWidth={2}
                  dot={{ r: 1, strokeWidth: 1 }}
                  connectNulls
                />
                {wltpKm != null && (
                  <Line
                    yAxisId="range100"
                    type="step"
                    dataKey="wltp"
                    name="WLTP"
                    stroke="#8b8fa3"
                    strokeWidth={1}
                    strokeDasharray="4 4"
                    dot={false}
                  />
                )}

              <Line
                  yAxisId="cons"
                  type="monotone"
                  dataKey="consumption"
                  name="Electric Consumption"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  dot={{ r: 1, strokeWidth: 1 }}
                  connectNulls
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <StatTable data={rangeAt100ChartData.length > 0 ? rangeAt100ChartData.map(d => ({ ...d, wltp: wltpKm ?? undefined })) : [{wltp: wltpKm ?? undefined}]} dataKeys={[
            { key: "range_estimated_full", label: "Range at 100% primary", color: "#4BA82E", unit: "km", decimals: 0 },
            { key: "consumption", label: "Electric Consumption primary", color: "#f59e0b", unit: "kWh/100km", decimals: 2 },
            { key: "wltp", label: "WLTP primary", color: "#4BA82E", unit: "km", decimals: 0 }
          ]} />
          </>
        ) : (
          <div className="h-[200px] flex flex-col items-center justify-center gap-1 text-iv-muted text-sm border border-dashed border-iv-border rounded-lg">
            <p>Range at 100% and WLTP will appear as the collector stores drive data.</p>
            <p className="text-xs">Electric consumption (kWh/100km) will be added when derived from drive data.</p>
          </div>
        )}
      </div>

      {/* 3. Efficiency (Grafana-style: range_estimated_full / wltp * 100 vs 100% reference) */}
      <div className="glass rounded-xl p-5">
        <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2">
          <BarChart3 size={14} /> Efficiency
        </h3>
        {efficiencyChartData.length > 0 ? (
          <>
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={efficiencyChartData.map((d) => ({
                  ...d,
                  ref100: 100,
                }))}
                margin={{ top: 8, right: 8, left: 8, bottom: 8 }}
              >
                <XAxis
                  dataKey="timeMs"
                  type="number"
                  domain={efficiencyDomain}
                  tickFormatter={(v) => {
                    const span = efficiencyDomain[1] - efficiencyDomain[0];
                    return span <= 24 * 60 * 60 * 1000
                      ? format(new Date(v), "HH:mm")
                      : format(new Date(v), "d MMM");
                  }}
                  stroke="#8b8fa3"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                />
                <CartesianGrid strokeDasharray="3 3" stroke="var(--iv-border)" opacity={0.5} />
                {bandTimestamps.map((band, i) => (
                  <ReferenceArea
                    key={`eff-${band.from_date}-${i}`}
                    x1={band.fromMs}
                    x2={band.toMs}
                    fill={STATE_COLORS[band.state] ?? "rgba(128,128,128,0.2)"}
                    strokeOpacity={0}
                  />
                ))}
                <YAxis
                  stroke="#8b8fa3"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${v}%`}
                  domain={['auto', 'auto']}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    return (
                      <div className="rounded-lg bg-iv-charcoal border border-iv-border px-3 py-2 shadow-xl">
                        <p className="text-xs text-iv-muted">
                          {label != null ? format(new Date(label as number), "d MMM HH:mm") : ""}
                        </p>
                        {payload.map((p) => (
                          <p key={p.dataKey} className="text-sm font-semibold text-iv-text">
                            {p.name}: {p.value != null ? `${Number(p.value).toFixed(1)}%` : "—"}
                          </p>
                        ))}
                      </div>
                    );
                  }}
                />
                <Area
                  type="step"
                  dataKey="efficiency_pct"
                  name="Efficiency primary"
                  stroke="#4BA82E"
                  fill="#4BA82E"
                  fillOpacity={0.2}
                  strokeWidth={2}
                  dot={{ r: 1, strokeWidth: 1 }}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="ref100"
                  name="100% = WLTP Range"
                  stroke="#8b8fa3"
                  strokeWidth={1}
                  strokeDasharray="4 4"
                  dot={{ r: 1, strokeWidth: 1 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <StatTable data={efficiencyChartData.map(d => ({...d, ref100: 100}))} dataKeys={[
            { key: "efficiency_pct", label: "Efficiency primary", color: "#4BA82E", unit: "%", decimals: 1 },
            { key: "ref100", label: "100% = WLTP Range", color: "#8b8fa3", unit: "%", decimals: 0 }
          ]} />
          </>
        ) : (
          <div className="h-[200px] flex items-center justify-center text-iv-muted text-sm border border-dashed border-iv-border rounded-lg">
            Efficiency vs WLTP will appear as drive data and WLTP are available.
          </div>
        )}
      </div>

      {/* 4. Charging: Power (kW) + Rate (km/h) */}
      {chargingChartData.length > 0 && (
        <div className="glass rounded-xl p-5">
          <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2">
            <Zap size={14} /> Charging Power & Rate
          </h3>
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={chargingChartData}
                margin={{ top: 8, right: 8, left: 8, bottom: 8 }}
              >
                <XAxis
                  dataKey="timeMs"
                  type="number"
                  domain={chargingDomain}
                  tickFormatter={(v) => {
                    const span = chargingDomain[1] - chargingDomain[0];
                    return span <= 24 * 60 * 60 * 1000
                      ? format(new Date(v), "HH:mm")
                      : format(new Date(v), "d MMM");
                  }}
                  stroke="#8b8fa3"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                />
                <CartesianGrid strokeDasharray="3 3" stroke="var(--iv-border)" opacity={0.5} />
                {bandTimestamps.map((band, i) => (
                  <ReferenceArea
                    key={`ch-${band.from_date}-${i}`}
                    yAxisId="power"
                    x1={band.fromMs}
                    x2={band.toMs}
                    fill={STATE_COLORS[band.state] ?? "rgba(128,128,128,0.2)"}
                    strokeOpacity={0}
                  />
                ))}
                <YAxis
                  yAxisId="power"
                  stroke="#8b8fa3"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${v} kW`}
                />
                <YAxis
                  yAxisId="rate"
                  orientation="right"
                  stroke="#8b8fa3"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${v} km/h`}
                />
                {(chargingChartData.some((d) => d.outside_temp != null || d.battery_temp != null)) && (
                  <YAxis
                    yAxisId="temp"
                    orientation="right"
                    stroke="#f59e0b"
                    fontSize={10}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `${v}°C`}
                  />
                )}
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    return (
                      <div className="rounded-lg bg-iv-charcoal border border-iv-border px-3 py-2 shadow-xl">
                        <p className="text-xs text-iv-muted">
                          {label != null ? format(new Date(label as number), "d MMM HH:mm") : ""}
                        </p>
                        {payload.map((p) => (
                          <p key={p.dataKey} className="text-sm font-semibold text-iv-text">
                            {p.name}: {p.value != null ? (p.dataKey === "power" ? `${p.value} kW` : p.dataKey === "rate" ? `${p.value} km/h` : `${p.value}°C`) : "—"}
                          </p>
                        ))}
                      </div>
                    );
                  }}
                />
                <Line
                  yAxisId="power"
                  type="monotone"
                  dataKey="power"
                  name="Charging Power"
                  stroke="#00D4FF"
                  strokeWidth={2}
                  dot={{ r: 1, strokeWidth: 1 }}
                  connectNulls
                />
                <Line
                  yAxisId="rate"
                  type="monotone"
                  dataKey="rate"
                  name="Charging Rate"
                  stroke="#4BA82E"
                  strokeWidth={2}
                  dot={{ r: 1, strokeWidth: 1 }}
                  connectNulls
                />

              </LineChart>
            </ResponsiveContainer>
          </div>
          <StatTable data={chargingChartData} dataKeys={[
            { key: "power", label: "Charging Power", color: "#00D4FF", unit: "kW", decimals: 1 },
            { key: "rate", label: "Charging Rate", color: "#4BA82E", unit: "km/h", decimals: 0 },
            { key: "outside_temp", label: "Outside Temperature", color: "#f59e0b", unit: "°C", decimals: 1 },
            { key: "battery_temp", label: "Battery Temperature", color: "#e11d48", unit: "°C", decimals: 1 }
          ]} />
        </div>
      )}



      {/* 5. States Timeline (Gantt-style) */}
      <div className="glass rounded-xl p-5 border border-iv-border">
        <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2">
          <Activity size={14} /> States Timeline
        </h3>
        <div className="space-y-4">
          {STATE_TOGGLES.map(({ id, label, icon: Icon }) => {
            const bands = stateBands.filter((b) => b.state === id);
            const spanMs = rangeToMs - rangeFromMs || 1;
            
            return (
              <div key={id} className="relative">
                <div className="flex items-center gap-3 mb-1">
                  <Icon size={14} className={cn(
                    id === "online" ? "text-iv-green" : 
                    id === "climatization" ? "text-amber-400" : 
                    id === "charging" ? "text-iv-cyan" : "text-purple-500"
                  )} />
                  <span className="text-xs font-semibold text-iv-text w-24">{label}</span>
                </div>
                <div className="relative h-6 w-full bg-iv-surface/50 rounded-md overflow-hidden border border-iv-border/50">
                  {bands.map((b, i) => {
                    const fromMs = new Date(b.from_date).getTime();
                    const toMs = new Date(b.to_date).getTime();
                    // Clamp to visible range
                    const leftMs = Math.max(rangeFromMs, fromMs);
                    const rightMs = Math.min(rangeToMs, toMs);
                    if (leftMs > rightMs) return null; // Outside range entirely
                    
                    const leftPct = ((leftMs - rangeFromMs) / spanMs) * 100;
                    const widthPct = ((rightMs - leftMs) / spanMs) * 100;
                    
                    return (
                      <div
                        key={i}
                        className={cn("absolute h-full rounded-sm opacity-80", 
                          id === "online" ? "bg-iv-green" : 
                          id === "climatization" ? "bg-amber-400" : 
                          id === "charging" ? "bg-iv-cyan" : "bg-purple-500"
                        )}
                        style={{ left: `${leftPct}%`, width: `${Math.max(widthPct, 0.5)}%` }}
                        title={`${format(new Date(fromMs), "d MMM HH:mm")} - ${format(new Date(toMs), "HH:mm")}`}
                      />
                    );
                  })}
                </div>
              </div>
            );
          })}
          <div className="flex justify-between text-[10px] text-iv-muted mt-2 border-t border-iv-border/50 pt-2">
            <span>{format(new Date(rangeFromMs), "d MMM HH:mm")}</span>
            <span>{format(new Date(rangeToMs), "d MMM HH:mm")}</span>
          </div>
        </div>
      </div>

      {/* Period summary (existing stats table + bar charts when available) */}
      {stats.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-iv-muted flex items-center gap-2">
            <BarChart3 size={14} /> Period summary
          </h3>
          <div className="glass rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-iv-border text-left text-xs text-iv-muted uppercase tracking-wider">
                    <th className="px-4 py-3">Period</th>
                    <th className="px-4 py-3">Drives</th>
                    <th className="px-4 py-3">Distance</th>
                    <th className="px-4 py-3">Charges</th>
                    <th className="px-4 py-3">Energy</th>
                    <th className="px-4 py-3">Avg/Session</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.map((s, i) => (
                    <tr key={i} className="border-b border-iv-border/50 hover:bg-iv-surface/50">
                      <td className="px-4 py-3 text-iv-text">{new Date(s.period).toLocaleDateString()}</td>
                      <td className="px-4 py-3 text-iv-green font-medium">{s.drives_count}</td>
                      <td className="px-4 py-3 text-iv-text">{s.total_distance_km.toFixed(1)} km</td>
                      <td className="px-4 py-3 text-iv-cyan font-medium">{s.charging_sessions_count}</td>
                      <td className="px-4 py-3 text-iv-text">{s.total_energy_kwh.toFixed(1)} kWh</td>
                      <td className="px-4 py-3 text-iv-muted">{s.avg_energy_per_session_kwh.toFixed(1)} kWh</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
