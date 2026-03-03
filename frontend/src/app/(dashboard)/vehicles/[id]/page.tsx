"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  Battery,
  Gauge,
  Plug,
  Car,
  Clock,
  Thermometer,
  ThermometerSnowflake,
  Zap,
  ZapOff,
  Lock,
  Unlock,
  Volume2,
  Power,
  Loader2,
  CheckCircle2,
  XCircle,
  Trash2,
  Wifi,
  WifiOff,
  MapPin,
  Wrench,
  BarChart3,
  DoorOpen,
  Wind,
  Activity,
  TrendingUp,
  Info,
  Cpu,
  LifeBuoy,
  Armchair,
  CircleDashed,
  Lightbulb,
  Circle,
  MoreHorizontal,
  AlertTriangle,
  RefreshCcw,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
} from "recharts";
import { api } from "@/lib/api";
import dynamic from "next/dynamic";

import { CarOverviewDashboard } from "@/components/statistics/CarOverviewDashboard";
import { ChargingSessionsDashboard } from "@/components/statistics/ChargingSessionsDashboard";
import { ChargingStatisticsDashboard } from "@/components/statistics/ChargingStatisticsDashboard";
import { DrivingStatisticsDashboard } from "@/components/statistics/DrivingStatisticsDashboard";
import { LocationsDashboard } from "@/components/statistics/LocationsDashboard";
import { VisitedDashboard } from "@/components/statistics/VisitedDashboard";
import { MileageKMDashboard } from "@/components/statistics/MileageKMDashboard";
import { TripsDashboard } from "@/components/statistics/TripsDashboard";

const LocationMap = dynamic(() => import("@/components/map"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 w-full h-full bg-iv-surface/20 animate-pulse" />,
});

type Tab = "overview" | "specifications" | "charging" | "trips" | "statistics" | "maintenance" | "commands";

interface Vehicle {
  id: string;
  display_name: string;
  manufacturer: string;
  model: string;
  model_year: number;
  collection_enabled: boolean;
  active_interval_seconds: number;
  parked_interval_seconds: number;
  image_url: string | null;
  body_type: string | null;
  trim_level: string | null;
  exterior_colour: string | null;
  battery_capacity_kwh: number | null;
  engine_power_kw: number | null;
  max_charging_power_kw: number | null;
  software_version: string | null;
  capabilities: Array<{ id: string; statuses: any[] }> | null;
  warning_lights: Array<{ category: string; defects: any[] }> | null;
  specifications: Record<string, any> | null;
  connector_status: string | null;
  created_at: string;
}

interface VehicleStatus {
  vin_last4: string;
  display_name: string;
  manufacturer: string;
  model: string;
  image_url: string | null;
  battery_capacity_kwh: number | null;
  latest_battery_level: number | null;
  latest_range_km: number | null;
  latest_charging_state: string | null;
  latest_vehicle_state: string | null;
  latest_position: { latitude: number; longitude: number } | null;
  last_updated: string | null;
  charging_power_kw: number | null;
  remaining_charge_time_min: number | null;
  target_soc: number | null;
  charge_type: string | null;
  doors_locked: string | null;
  doors_open: string | null;
  windows_open: string | null;
  lights_on: string | null;
  trunk_open: boolean | null;
  bonnet_open: boolean | null;
  climate_state: string | null;
  target_temp: number | null;
  outside_temp: number | null;
  odometer_km: number | null;
  inspection_due_days: number | null;
  is_online: boolean | null;
  is_in_motion: boolean | null;
  connector_status: string | null;
}

interface BatteryPoint { timestamp: string; level: number }
interface RangePoint { timestamp: string; range_km: number }
interface ChargingSession {
  id: string; session_start: string; session_end: string | null;
  start_level: number; end_level: number | null; charging_type: string;
  energy_kwh: number | null;
}
interface Trip {
  id: string; start_date: string; end_date: string | null;
  start_odometer: number; end_odometer: number | null;
}
interface MaintenanceItem {
  captured_at: string; mileage_in_km: number | null;
  inspection_due_in_days: number | null; inspection_due_in_km: number | null;
  oil_service_due_in_days: number | null; oil_service_due_in_km: number | null;
}
interface OdometerItem { captured_at: string; mileage_in_km: number }
interface StatItem {
  period: string; drives_count: number; total_distance_km: number;
  charging_sessions_count: number; total_energy_kwh: number;
  avg_energy_per_session_kwh: number;
}

const tabs: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: "overview", label: "Overview", icon: Car },
  { key: "specifications", label: "Specifications", icon: Info },
  { key: "charging", label: "Charging", icon: Zap },
  { key: "trips", label: "Trips", icon: MapPin },
  { key: "statistics", label: "Statistics", icon: BarChart3 },
  { key: "maintenance", label: "Maintenance", icon: Wrench },
  { key: "commands", label: "Commands", icon: Power },
];

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
function formatDate(ts: string) {
  return new Date(ts).toLocaleDateString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
function formatRelative(ts: string) {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function formatChargingState(state: string | null | undefined): string {
  if (!state) return "—";
  if (state === "CONNECT_CABLE" || state === "DISCONNECTED") return "Disconnected";
  if (state === "READY_FOR_CHARGING") return "Ready to Charge";
  if (state === "CHARGING") return "Charging";
  if (state === "ERROR") return "Error";
  return state.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
}

function ChartTooltipContent({ active, payload, label, unit }: {
  active?: boolean; payload?: Array<{ value: number }>; label?: string; unit: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg bg-iv-charcoal border border-iv-border px-3 py-2 shadow-xl">
      <p className="text-xs text-iv-muted">{label}</p>
      <p className="text-sm font-semibold text-iv-text">{payload[0].value}{unit}</p>
    </div>
  );
}

function EmptyState({ icon: Icon, message }: { icon: React.ElementType; message: string }) {
  return (
    <div className="glass rounded-xl p-12 text-center">
      <Icon size={32} className="mx-auto mb-3 text-iv-muted" />
      <p className="text-sm text-iv-muted">{message}</p>
    </div>
  );
}

function StatusPill({ label, value, icon: Icon, accent = "green" }: {
  label: string; value: string | number | null; icon: React.ElementType; accent?: "green" | "cyan" | "warning" | "muted";
}) {
  const accentMap = { green: "text-iv-green", cyan: "text-iv-cyan", warning: "text-iv-warning", muted: "text-iv-muted" };
  return (
    <div className="glass rounded-xl p-4 flex flex-col gap-1.5 min-w-0">
      <div className="flex items-center gap-2 text-iv-muted">
        <Icon size={14} />
        <span className="text-xs font-medium uppercase tracking-wider truncate">{label}</span>
      </div>
      <p className={`text-lg font-bold truncate ${accentMap[accent]}`}>{value ?? "—"}</p>
    </div>
  );
}

function CommandButton({ icon: Icon, label, onClick, loading, variant = "default" }: {
  icon: React.ElementType; label: string; onClick: () => void; loading: boolean; variant?: "default" | "danger";
}) {
  return (
    <button onClick={onClick} disabled={loading}
      className={`glass rounded-xl p-4 flex flex-col items-center gap-3 transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed ${
        variant === "danger" ? "hover:border-iv-danger/40" : "hover:border-iv-green/40"
      }`}>
      {loading ? <Loader2 size={24} className="animate-spin text-iv-muted" /> :
        <Icon size={24} className={variant === "danger" ? "text-iv-danger" : "text-iv-green"} />}
      <span className="text-xs font-medium text-iv-text">{label}</span>
    </button>
  );
}

function CommandResult({ status, message }: { status: "success" | "error"; message: string }) {
  return (
    <div className={`flex items-center gap-2 rounded-lg px-4 py-3 text-sm ${
      status === "success" ? "bg-iv-green/10 text-iv-green" : "bg-iv-danger/10 text-iv-danger"
    }`}>
      {status === "success" ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
      {message}
    </div>
  );
}

function WarningLightPill({ category, defects }: { category: string; defects: any[] }) {
  const isOk = !defects || defects.length === 0;
  
  const iconMap: Record<string, React.ElementType> = {
    "ASSISTANCE": LifeBuoy,
    "COMFORT": Armchair,
    "BRAKE": CircleDashed,
    "ELECTRIC_ENGINE": Cpu,
    "LIGHTING": Lightbulb,
    "TIRE": Circle,
    "OTHER": MoreHorizontal,
  };
  const Icon = iconMap[category.toUpperCase()] || AlertTriangle;
  const name = category.replace(/_/g, " ").toLowerCase();

  return (
    <div className={`relative group flex items-center gap-2 rounded-xl p-2.5 border transition-all ${
      isOk 
        ? "bg-iv-surface/30 border-iv-border/50 text-iv-muted hover:border-iv-green/30" 
        : "bg-iv-danger/10 border-iv-danger/40 text-iv-danger shadow-[0_0_15px_-3px_rgba(220,38,38,0.2)]"
    }`}>
      <div className={`flex items-center justify-center rounded-full p-1.5 ${isOk ? "bg-iv-surface" : "bg-iv-danger/20"}`}>
        <Icon size={14} className={isOk ? "text-iv-green" : "text-iv-danger"} />
      </div>
      <div className="flex-1 min-w-0">
        <p className={`text-[10px] sm:text-[11px] font-bold uppercase tracking-wide truncate ${isOk ? "text-iv-text" : "text-iv-danger"}`} title={name}>
          {name}
        </p>
        <p className="text-[9px] sm:text-[10px] font-medium truncate text-iv-muted">
          {isOk ? "OK" : `${defects.length} Issue${defects.length > 1 ? "s" : ""}`}
        </p>
      </div>

      {/* Tooltip for defects */}
      {!isOk && (
        <div className="absolute top-full left-0 mt-2 z-50 hidden group-hover:block w-48 p-2.5 rounded-lg bg-iv-charcoal border border-iv-danger/50 shadow-xl backdrop-blur-xl">
          <p className="text-xs font-semibold text-iv-danger mb-1.5 uppercase tracking-wider border-b border-iv-danger/20 pb-1">{name} Issues</p>
          <ul className="space-y-1.5">
            {defects.map((d, i) => {
              const text = typeof d === "string" ? d : (d.description || d.text || JSON.stringify(d));
              return (
                <li key={i} className="text-[10px] text-white leading-tight flex items-start gap-1">
                  <span className="text-iv-danger mt-0.5">•</span>
                  <span>{text}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function VehicleDetailPage() {
  const params = useParams();
  const router = useRouter();
  const vehicleId = params.id as string;

  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [status, setStatus] = useState<VehicleStatus | null>(null);
  const [batteryHistory, setBatteryHistory] = useState<BatteryPoint[]>([]);
  const [rangeHistory, setRangeHistory] = useState<RangePoint[]>([]);
  const [sessions, setSessions] = useState<ChargingSession[]>([]);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [maintenance, setMaintenance] = useState<MaintenanceItem[]>([]);
  const [odometer, setOdometer] = useState<OdometerItem[]>([]);
  const [stats, setStats] = useState<StatItem[]>([]);
  const [statPeriod, setStatPeriod] = useState<"day" | "week" | "month" | "year">("day");
  

  const [refreshLoading, setRefreshLoading] = useState(false);
  const [refreshToast, setRefreshToast] = useState<{ status: "success" | "error"; message: string } | null>(null);

  const [cmdLoading, setCmdLoading] = useState<string | null>(null);
  const [cmdResult, setCmdResult] = useState<{ status: "success" | "error"; message: string } | null>(null);
  const [climateTemp, setClimateTemp] = useState("21");
  const [unlockSpin, setUnlockSpin] = useState("");
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [v, s] = await Promise.all([api.getVehicle(vehicleId), api.getVehicleStatus(vehicleId)]);
      setVehicle(v);
      setStatus(s);
    } catch { router.replace("/"); }
    finally { setLoading(false); }
  }, [vehicleId, router]);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    if (tab === "overview") {
      Promise.all([api.getBatteryHistory(vehicleId, 200), api.getRangeHistory(vehicleId, 200)])
        .then(([b, r]) => { setBatteryHistory(b); setRangeHistory(r); });
    } else if (tab === "charging") {
      api.getChargingSessions(vehicleId, 50).then(setSessions);
    } else if (tab === "trips") {
      api.getTrips(vehicleId, 50).then(setTrips);
    } else if (tab === "statistics") {
      api.getStatistics(vehicleId, statPeriod, 30).then(setStats);
    } else if (tab === "maintenance") {
      Promise.all([api.getMaintenance(vehicleId, 50), api.getOdometer(vehicleId, 200)])
        .then(([m, o]) => { setMaintenance(m); setOdometer(o); });
    }
  }, [tab, vehicleId, statPeriod]);

  const runCommand = async (command: string, body?: object) => {
    setCmdLoading(command); setCmdResult(null);
    try {
      const res = await api.sendCommand(vehicleId, command, body);
      setCmdResult({ status: "success", message: res.message || "Command sent successfully" });
    } catch (err) {
      setCmdResult({ status: "error", message: err instanceof Error ? err.message : "Command failed" });
    } finally { setCmdLoading(null); }
  };

  const handleRefresh = async () => {
    setRefreshLoading(true);
    setRefreshToast(null);
    try {
      await api.refreshVehicle(vehicleId);
      setRefreshToast({ status: "success", message: "Refresh queued — telemetry fetch will run shortly" });
    } catch (err) {
      setRefreshToast({ status: "error", message: err instanceof Error ? err.message : "Refresh failed" });
    } finally {
      setRefreshLoading(false);
      setTimeout(() => setRefreshToast(null), 5000);
    }
  };

  const handleDelete = async () => {
    setDeleteLoading(true);
    try { await api.deleteVehicle(vehicleId); router.replace("/"); }
    catch { setDeleteLoading(false); setShowDeleteModal(false); }
  };

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-iv-border border-t-iv-green" />
          <p className="text-sm text-iv-muted">Loading vehicle...</p>
        </div>
      </div>
    );
  }

  if (!vehicle || !status) return null;

  const imgSrc = vehicle.image_url || status.image_url;

  return (
    <div className="mx-auto max-w-6xl space-y-6 overflow-x-hidden">
      {/* Header */}
      <div className="flex flex-wrap items-start gap-3">
        <Link href="/"
          className="mt-1 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border border-iv-border bg-iv-surface text-iv-muted transition-colors hover:text-iv-text hover:border-iv-green/40">
          <ArrowLeft size={18} />
        </Link>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-iv-text truncate">
              {vehicle.display_name || (vehicle.model.toLowerCase().includes(vehicle.manufacturer.toLowerCase()) ? vehicle.model : `${vehicle.manufacturer} ${vehicle.model}`)}
            </h1>
            {status.is_online !== null && (
              status.is_online
                ? <Wifi size={16} className="text-iv-green flex-shrink-0" />
                : <WifiOff size={16} className="text-iv-muted flex-shrink-0" />
            )}
          </div>
          <div className="flex items-center gap-3 mt-1 text-sm text-iv-muted flex-wrap">
            <span>
              {vehicle.model.toLowerCase().includes(vehicle.manufacturer.toLowerCase()) ? vehicle.model : `${vehicle.manufacturer} ${vehicle.model}`}
              {vehicle.trim_level ? ` ${vehicle.trim_level}` : ""}
              {vehicle.model_year ? ` ${vehicle.model_year}` : ""}
            </span>
            {status.vin_last4 && (
              <>
                <span className="text-iv-border">·</span>
                <span className="font-mono text-xs bg-iv-surface px-2 py-0.5 rounded">VIN ···{status.vin_last4}</span>
              </>
            )}
            {status.odometer_km != null && (
              <>
                <span className="text-iv-border">·</span>
                <span>{status.odometer_km.toLocaleString()} km</span>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 mt-1 ml-auto">
          <button
            onClick={handleRefresh}
            disabled={refreshLoading}
            title="Trigger a one-time full telemetry fetch"
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium border border-iv-border text-iv-muted hover:text-iv-green hover:border-iv-green/40 hover:bg-iv-green/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {refreshLoading
              ? <Loader2 size={16} className="animate-spin" />
              : <RefreshCcw size={16} />}
            <span className="hidden sm:inline">Refresh</span>
          </button>
          <button onClick={() => setShowDeleteModal(true)}
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium border border-iv-border text-iv-muted hover:text-iv-danger hover:border-iv-danger/40 hover:bg-iv-danger/10 transition-all">
            <Trash2 size={16} />
            <span className="hidden sm:inline">Delete</span>
          </button>
        </div>
      </div>

      {/* Refresh toast notification */}
      {refreshToast && (
        <div className={`flex items-center gap-2 rounded-lg px-4 py-3 text-sm ${
          refreshToast.status === "success"
            ? "bg-iv-green/10 text-iv-green border border-iv-green/20"
            : "bg-iv-danger/10 text-iv-danger border border-iv-danger/20"
        }`}>
          {refreshToast.status === "success"
            ? <CheckCircle2 size={16} />
            : <XCircle size={16} />}
          {refreshToast.message}
        </div>
      )}

      {/* Hero: map (Last Known Position) + car image */}
      {/* Mobile: flex-col → Map on top, Car below, vertical fade at boundary */}
      {/* Desktop (md+): flex-row → Map on left, Car on right, horizontal fade at boundary */}
      {(imgSrc || status.latest_position) && (
        <div className="glass rounded-2xl overflow-hidden bg-[var(--iv-charcoal)] border border-[var(--iv-border)]">
          <div className="relative flex flex-col md:flex-row md:min-h-[300px]">

            {/* ── Map panel (top on mobile / left on desktop) ── */}
            {status.latest_position ? (
              <div className="relative flex-1 min-h-[260px] md:min-h-[300px] bg-[var(--iv-charcoal)]">
                {/* Map fills the entire panel */}
                <div className="absolute inset-0">
                  <LocationMap
                    latitude={status.latest_position.latitude}
                    longitude={status.latest_position.longitude}
                  />
                </div>

                {/* ── Vertical fade (mobile only) ──
                    Fades the bottom edge of the map downward into the car section */}
                <div
                  className="pointer-events-none absolute inset-x-0 bottom-0 z-[400] h-12 md:hidden"
                  style={{ background: "linear-gradient(to bottom, transparent, var(--iv-charcoal))" }}
                />

                {/* ── Horizontal fade (desktop only) ──
                    Fades the right edge of the map into the car section */}
                <div
                  className="pointer-events-none absolute inset-y-0 right-0 z-[400] hidden w-16 md:block"
                  style={{ background: "linear-gradient(to right, transparent, var(--iv-charcoal))" }}
                />

                {/* Open in Maps button */}
                <div className="absolute top-3 left-3 z-[401]">
                  <a
                    href={`https://www.google.com/maps?q=${status.latest_position.latitude},${status.latest_position.longitude}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium bg-iv-charcoal/90 text-iv-cyan border border-iv-border/50 hover:bg-iv-surface transition-colors shadow-sm backdrop-blur-md"
                  >
                    <MapPin size={16} className="text-iv-cyan" />
                    Open in Maps
                  </a>
                </div>

                {/* Coordinates Label */}
                <div className="absolute bottom-3 left-3 z-[401]">
                  <span className="text-xs font-mono text-iv-muted truncate bg-iv-charcoal/90 px-2 py-1.5 rounded-md backdrop-blur-md shadow-sm border border-iv-border/50">
                    {status.latest_position.latitude.toFixed(5)}, {status.latest_position.longitude.toFixed(5)}
                  </span>
                </div>
              </div>
            ) : (
              <div className="flex flex-1 flex-col items-center justify-center py-8 px-4 min-h-[200px] md:min-h-[300px] text-iv-muted/50">
                <MapPin size={40} strokeWidth={1.5} />
                <p className="mt-2 text-sm">No position data yet</p>
              </div>
            )}

            {/* ── Car image panel (bottom on mobile / right on desktop) ── */}
            <div className="relative z-20 flex flex-col items-center justify-center p-6 min-h-[200px] md:min-h-[300px] bg-[var(--iv-charcoal)] flex-1 md:flex-none md:w-[45%]">
              {imgSrc ? (
                <img src={imgSrc} alt={vehicle.display_name} className="max-h-60 object-contain drop-shadow-2xl" />
              ) : (
                <div className="flex flex-col items-center gap-2 text-iv-muted/40">
                  <Car size={48} strokeWidth={1.5} />
                  <span className="text-sm">No image</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Status Bar */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatusPill label="Battery" icon={Battery} accent="green"
          value={status.latest_battery_level != null ? `${status.latest_battery_level}%` : null} />
        <StatusPill label="Range" icon={Gauge} accent="cyan"
          value={status.latest_range_km != null ? `${Math.round(status.latest_range_km)} km` : null} />
        <StatusPill label="Charging" icon={Plug} 
          accent={status.latest_charging_state === "CHARGING" ? "green" : status.latest_charging_state === "CONNECT_CABLE" ? "muted" : "warning"} 
          value={formatChargingState(status.latest_charging_state)} />
        <StatusPill label="Climate" icon={Wind} accent="muted"
          value={status.climate_state === "INVALID" ? "OFF" : (status.climate_state || (status.outside_temp != null ? `${status.outside_temp}°C` : null))} />
        <StatusPill label="Lock" icon={Lock} accent={status.doors_locked?.toLowerCase().includes("locked") ? "green" : "warning"}
          value={status.doors_locked || status.latest_vehicle_state} />
        <StatusPill label="Updated" icon={Clock} accent="muted"
          value={status.last_updated ? formatRelative(status.last_updated) : null} />
      </div>

      {/* Warning Lights */}
      {vehicle.warning_lights && vehicle.warning_lights.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7 mb-6">
          {vehicle.warning_lights.map((wl, idx) => (
            <WarningLightPill key={idx} category={wl.category} defects={wl.defects} />
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-nowrap gap-1 rounded-xl bg-iv-surface p-1 overflow-x-auto no-scrollbar md:justify-center">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 flex-shrink-0 rounded-lg px-3 py-2 text-sm font-medium transition-all ${
              tab === t.key ? "bg-iv-green/15 text-iv-green shadow-sm" : "text-iv-muted hover:text-iv-text"
            }`}>
            <t.icon size={14} />
            {t.label}
          </button>
        ))}
      </div>

      {/* ===== OVERVIEW ===== */}
      {tab === "overview" && (
        <div className="space-y-4">
          {/* Vehicle Status Panel */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="glass rounded-xl p-5">
              <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2">
                <DoorOpen size={14} /> Vehicle Status
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <StatusRow label="Doors" value={status.doors_open || "All closed"} ok={!status.doors_open} />
                <StatusRow label="Windows" value={status.windows_open || "All closed"} ok={!status.windows_open} />
                <StatusRow label="Trunk" value={status.trunk_open ? "Open" : "Closed"} ok={!status.trunk_open} />
                <StatusRow label="Bonnet" value={status.bonnet_open ? "Open" : "Closed"} ok={!status.bonnet_open} />
                <StatusRow label="Lights" value={status.lights_on || "All off"} ok={!status.lights_on} />
                <StatusRow label="Motion" value={status.is_in_motion ? "Moving" : "Parked"} ok={!status.is_in_motion} />
              </div>
            </div>

            <div className="glass rounded-xl p-5">
              <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2">
                <Activity size={14} /> Charging Details
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <StatusRow label="State" value={formatChargingState(status.latest_charging_state)} />
                <StatusRow label="Type" value={status.charge_type || "—"} />
                <StatusRow label="Power" value={status.charging_power_kw != null ? `${status.charging_power_kw} kW` : "—"} />
                <StatusRow label="Time Left" value={status.remaining_charge_time_min != null ? `${status.remaining_charge_time_min} min` : "—"} />
                <StatusRow label="Target SoC" value={status.target_soc != null ? `${status.target_soc}%` : "—"} />
                <StatusRow label="Inspection" value={status.inspection_due_days != null ? `${status.inspection_due_days} days` : "—"} />
              </div>
            </div>
          </div>

          {/* Climate panel */}
          {(status.climate_state || status.target_temp != null || status.outside_temp != null) && (
            <div className="glass rounded-xl p-5">
              <h3 className="text-sm font-medium text-iv-muted mb-3 flex items-center gap-2">
                <Thermometer size={14} /> Climate
              </h3>
              <div className="flex gap-6 text-sm">
                {status.climate_state && <span>State: <strong className="text-iv-text">{status.climate_state}</strong></span>}
                {status.target_temp != null && <span>Target: <strong className="text-iv-cyan">{status.target_temp}°C</strong></span>}
                {status.outside_temp != null && <span>Outside: <strong className="text-iv-text">{status.outside_temp}°C</strong></span>}
              </div>
            </div>
          )}

          {/* Charts */}
          <div className="glass rounded-xl p-5">
            <h3 className="text-sm font-medium text-iv-muted mb-4">Battery Level</h3>
            {batteryHistory.length === 0 ? (
              <div className="flex h-[240px] items-center justify-center"><p className="text-sm text-iv-muted">No battery data yet</p></div>
            ) : (
              <div className="h-[240px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={batteryHistory.slice().reverse().map(d => ({ time: formatTime(d.timestamp), value: d.level }))}>
                    <defs><linearGradient id="greenGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#4BA82E" stopOpacity={0.4} /><stop offset="100%" stopColor="#4BA82E" stopOpacity={0} /></linearGradient></defs>
                    <XAxis dataKey="time" stroke="#8b8fa3" fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis domain={[0, 100]} stroke="#8b8fa3" fontSize={11} tickLine={false} axisLine={false} tickFormatter={v => `${v}%`} />
                    <Tooltip content={<ChartTooltipContent unit="%" />} />
                    <Area type="monotone" dataKey="value" stroke="#4BA82E" strokeWidth={2} fill="url(#greenGrad)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          <div className="glass rounded-xl p-5">
            <h3 className="text-sm font-medium text-iv-muted mb-4">Range</h3>
            {rangeHistory.length === 0 ? (
              <div className="flex h-[240px] items-center justify-center"><p className="text-sm text-iv-muted">No range data yet</p></div>
            ) : (
              <div className="h-[240px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={rangeHistory.slice().reverse().map(d => ({ time: formatTime(d.timestamp), value: d.range_km }))}>
                    <defs><linearGradient id="cyanGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#00D4FF" stopOpacity={0.4} /><stop offset="100%" stopColor="#00D4FF" stopOpacity={0} /></linearGradient></defs>
                    <XAxis dataKey="time" stroke="#8b8fa3" fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis stroke="#8b8fa3" fontSize={11} tickLine={false} axisLine={false} tickFormatter={v => `${v} km`} />
                    <Tooltip content={<ChartTooltipContent unit=" km" />} />
                    <Area type="monotone" dataKey="value" stroke="#00D4FF" strokeWidth={2} fill="url(#cyanGrad)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Position */}
          {status.latest_position && (
            <div className="glass rounded-xl p-5">
              <h3 className="text-sm font-medium text-iv-muted mb-3 flex items-center gap-2">
                <MapPin size={14} /> Last Known Position
              </h3>
              <div className="flex items-center gap-4 text-sm">
                <span className="font-mono text-iv-text">
                  {status.latest_position.latitude.toFixed(5)}, {status.latest_position.longitude.toFixed(5)}
                </span>
                <a
                  href={`https://www.google.com/maps?q=${status.latest_position.latitude},${status.latest_position.longitude}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-iv-cyan hover:underline"
                >
                  Open in Maps
                </a>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ===== SPECIFICATIONS ===== */}
      {tab === "specifications" && (
        <div className="space-y-4">
          {vehicle.specifications?.renders && Array.isArray(vehicle.specifications.renders) && vehicle.specifications.renders.length > 0 && (
            <div className="glass rounded-xl p-5">
              <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2">
                <Car size={14} /> Exterior & Interior
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                {vehicle.specifications.renders.map((render: any, idx: number) => (
                  <div key={idx} className="relative aspect-[4/3] rounded-lg overflow-hidden bg-iv-surface border border-iv-border/50 group">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={render.url}
                      alt={render.viewType}
                      className="absolute inset-0 w-full h-full object-cover transition-transform duration-300 group-hover:scale-110"
                    />
                    <div className="absolute inset-x-0 bottom-0 p-2 bg-gradient-to-t from-black/80 to-transparent">
                      <p className="text-[10px] uppercase font-semibold text-white truncate text-center">
                        {render.viewType.replace(/_/g, ' ')}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Specs Panel */}
            {vehicle.specifications && (
              <div className="glass rounded-xl p-5 lg:col-span-1">
                <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2">
                  <Info size={14} /> Details
                </h3>
                <div className="grid grid-cols-1 gap-2 text-sm">
                  {vehicle.specifications.body && <StatusRow label="Body" value={vehicle.specifications.body} />}
                  {vehicle.specifications.trimLevel && <StatusRow label="Trim Level" value={vehicle.specifications.trimLevel} />}
                  {vehicle.specifications.exteriorColour && <StatusRow label="Exterior Colour" value={vehicle.specifications.exteriorColour} />}
                  {vehicle.specifications.manufacturingDate && <StatusRow label="Manufacturing Date" value={vehicle.specifications.manufacturingDate} />}
                  {vehicle.specifications.battery?.capacityInKWh && <StatusRow label="Battery Capacity" value={`${vehicle.specifications.battery.capacityInKWh} kWh`} />}
                  {vehicle.specifications.maxChargingPowerInKW && <StatusRow label="Max Charging Power" value={`${vehicle.specifications.maxChargingPowerInKW} kW`} />}
                  {vehicle.specifications.engine?.powerInKW && <StatusRow label="Engine Power" value={`${vehicle.specifications.engine.powerInKW} kW`} />}
                  {vehicle.specifications.gearbox?.type && <StatusRow label="Gearbox Type" value={vehicle.specifications.gearbox.type} />}
                  {vehicle.specifications.exteriorDimensions && (
                    <StatusRow 
                      label="Dimensions (L x W x H)" 
                      value={`${vehicle.specifications.exteriorDimensions.lengthInMm} x ${vehicle.specifications.exteriorDimensions.widthInMm} x ${vehicle.specifications.exteriorDimensions.heightInMm} mm`} 
                    />
                  )}
                </div>
              </div>
            )}

            {/* Capabilities Panel */}
            {vehicle.capabilities && vehicle.capabilities.length > 0 && (
              <div className="glass rounded-xl p-5 lg:col-span-2">
                <h3 className="text-sm font-medium text-iv-muted mb-4 flex items-center gap-2">
                  <Cpu size={14} /> Features & Capabilities
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {vehicle.capabilities.map((cap) => {
                    const name = cap.id.replace(/_/g, ' ').toLowerCase();
                    const isEnabled = !cap.statuses || cap.statuses.length === 0;
                    return (
                      <div key={cap.id} className="flex flex-col rounded-lg bg-iv-surface p-3 border border-iv-border/50">
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-xs font-semibold text-iv-text capitalize truncate" title={name}>
                            {name}
                          </span>
                          {isEnabled ? (
                            <CheckCircle2 size={14} className="text-iv-green shrink-0" />
                          ) : (
                            <span className="flex h-3 w-3 rounded-full bg-iv-warning/20 items-center justify-center shrink-0">
                              <span className="h-1.5 w-1.5 rounded-full bg-iv-warning"></span>
                            </span>
                          )}
                        </div>
                        <div className="text-[10px] text-iv-muted line-clamp-2">
                          {isEnabled ? "Enabled and active" : "Status conditional or requires attention"}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ===== CHARGING ===== */}
      {tab === "charging" && (
        <div className="space-y-4">
          {/* Current charging info */}
          {status.latest_charging_state && (
            <div className="glass rounded-xl p-5">
              <h3 className="text-sm font-medium text-iv-muted mb-3">Current Charging Status</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-iv-muted">State</p>
                  <p className={`text-sm font-semibold ${status.latest_charging_state === "CHARGING" ? "text-iv-green" : "text-iv-text"}`}>
                    {formatChargingState(status.latest_charging_state)}
                  </p>
                </div>
                <div><p className="text-xs text-iv-muted">Power</p><p className="text-sm font-semibold text-iv-text">{status.charging_power_kw != null ? `${status.charging_power_kw} kW` : "—"}</p></div>
                <div><p className="text-xs text-iv-muted">Time Remaining</p><p className="text-sm font-semibold text-iv-text">{status.remaining_charge_time_min != null ? `${status.remaining_charge_time_min} min` : "—"}</p></div>
                <div><p className="text-xs text-iv-muted">Target SoC</p><p className="text-sm font-semibold text-iv-cyan">{status.target_soc != null ? `${status.target_soc}%` : "—"}</p></div>
              </div>
            </div>
          )}

          {/* Sessions */}
          <ChargingSessionsDashboard vehicleId={vehicleId} />
        </div>
      )}

      {/* ===== TRIPS ===== */}

      {tab === "trips" && (
        <div className="space-y-3">
          {trips.length === 0 ? (
            <EmptyState icon={Car} message="No trips recorded yet" />
          ) : (
            <>
              <div className="glass rounded-xl p-5">
                <h3 className="text-sm font-medium text-iv-muted mb-2">Trip Summary</h3>
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div>
                    <p className="text-2xl font-bold text-iv-green">{trips.length}</p>
                    <p className="text-xs text-iv-muted">Total Trips</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-iv-cyan">
                      {trips.reduce((acc, t) => acc + (t.end_odometer && t.start_odometer ? t.end_odometer - t.start_odometer : 0), 0).toFixed(0)}
                    </p>
                    <p className="text-xs text-iv-muted">Total km</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-iv-text">
                      {trips.length > 0 ? (trips.reduce((acc, t) => acc + (t.end_odometer && t.start_odometer ? t.end_odometer - t.start_odometer : 0), 0) / trips.length).toFixed(1) : "0"}
                    </p>
                    <p className="text-xs text-iv-muted">Avg km/trip</p>
                  </div>
                </div>
              </div>
              {trips.map((t) => {
                const distance = t.end_odometer != null && t.start_odometer != null ? (t.end_odometer - t.start_odometer).toFixed(1) : null;
                return (
                  <div key={t.id} className="glass rounded-xl p-4 flex flex-col sm:flex-row sm:items-center gap-3">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-iv-cyan/10">
                        <Car size={18} className="text-iv-cyan" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-iv-text truncate">
                          {formatDate(t.start_date)}{t.end_date && ` → ${formatDate(t.end_date)}`}
                        </p>
                      </div>
                    </div>
                    {distance && <span className="text-iv-cyan font-mono text-sm font-semibold flex-shrink-0">{distance} km</span>}
                  </div>
                );
              })}
            </>
          )}
        </div>
      )}

      {/* ===== STATISTICS ===== */}
      {tab === "statistics" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="glass p-6 rounded-2xl border border-iv-border">
              <p className="text-sm text-iv-text-muted mb-2 flex items-center gap-2"><MapPin className="w-4 h-4 text-iv-cyan"/> All-Time Distance</p>
              <p className="text-3xl font-bold text-iv-text">{vehicle.specifications?.mileage_km ? vehicle.specifications.mileage_km.toLocaleString() : "--"} <span className="text-lg text-iv-text-muted font-normal">km</span></p>
            </div>
            <div className="glass p-6 rounded-2xl border border-iv-border">
              <p className="text-sm text-iv-text-muted mb-2 flex items-center gap-2"><Zap className="w-4 h-4 text-amber-500"/> Current Range</p>
              <p className="text-3xl font-bold text-iv-text">{vehicle.specifications?.range_km || "--"} <span className="text-lg text-iv-text-muted font-normal">km</span></p>
            </div>
            <div className="glass p-6 rounded-2xl border border-iv-border">
              <p className="text-sm text-iv-text-muted mb-2 flex items-center gap-2"><Battery className="w-4 h-4 text-iv-green"/> Current Level</p>
              <p className="text-3xl font-bold text-iv-text">{vehicle.specifications?.battery_percent || "--"} <span className="text-lg text-iv-text-muted font-normal">%</span></p>
            </div>
          </div>

          <div className="glass rounded-2xl p-5 sm:p-8 flex flex-col sm:flex-row items-center justify-between gap-4 border border-iv-border">
            <div className="text-center sm:text-left">
              <h2 className="text-xl font-bold text-iv-text mb-2 flex items-center justify-center sm:justify-start gap-2">
                <BarChart3 className="w-6 h-6 text-iv-cyan" />
                Advanced BI Analytics Hub
              </h2>
              <p className="text-iv-text-muted max-w-md text-sm">
                Access interactive charts, period-over-period comparisons, charging economics, and winter penalty curves.
              </p>
            </div>
            <Link 
              href={`/vehicles/${vehicleId}/statistics`}
              className="inline-flex items-center gap-2 bg-iv-cyan text-white px-6 py-3 rounded-xl font-medium hover:bg-iv-cyan/90 transition-colors shrink-0"
            >
              Launch Statistics
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      )}

      {/* ===== MAINTENANCE ===== */}


      {tab === "maintenance" && (
        <div className="space-y-4">
          {/* Current status */}
          {maintenance.length > 0 && (
            <div className="glass rounded-xl p-5">
              <h3 className="text-sm font-medium text-iv-muted mb-4">Current Maintenance Status</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-iv-muted">Odometer</p>
                  <p className="text-lg font-bold text-iv-text">
                    {maintenance[0].mileage_in_km != null ? `${maintenance[0].mileage_in_km.toLocaleString()} km` : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-iv-muted">Inspection Due</p>
                  <p className="text-lg font-bold text-iv-warning">
                    {maintenance[0].inspection_due_in_days != null ? `${maintenance[0].inspection_due_in_days} days` : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-iv-muted">Inspection km</p>
                  <p className="text-lg font-bold text-iv-text">
                    {maintenance[0].inspection_due_in_km != null ? `${maintenance[0].inspection_due_in_km.toLocaleString()} km` : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-iv-muted">Oil Service</p>
                  <p className="text-lg font-bold text-iv-text">
                    {maintenance[0].oil_service_due_in_days != null ? `${maintenance[0].oil_service_due_in_days} days` : "—"}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Mileage chart */}
          {odometer.length > 0 && (
            <div className="glass rounded-xl p-5">
              <h3 className="text-sm font-medium text-iv-muted mb-4">Mileage Over Time</h3>
              <div className="h-[280px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={odometer.slice().reverse().map(o => ({
                    time: new Date(o.captured_at).toLocaleDateString([], { month: "short", day: "numeric" }),
                    km: o.mileage_in_km,
                  }))}>
                    <XAxis dataKey="time" stroke="#8b8fa3" fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis stroke="#8b8fa3" fontSize={11} tickLine={false} axisLine={false} tickFormatter={v => `${(v / 1000).toFixed(0)}k`} />
                    <Tooltip content={<ChartTooltipContent unit=" km" />} />
                    <Line type="monotone" dataKey="km" stroke="#4BA82E" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* History */}
          {maintenance.length === 0 ? (
            <EmptyState icon={Wrench} message="No maintenance data yet" />
          ) : (
            <div className="glass rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-iv-border text-left text-xs text-iv-muted uppercase tracking-wider">
                      <th className="px-4 py-3">Date</th>
                      <th className="px-4 py-3">Mileage</th>
                      <th className="px-4 py-3">Inspection Due</th>
                      <th className="px-4 py-3">Oil Service Due</th>
                    </tr>
                  </thead>
                  <tbody>
                    {maintenance.map((m, i) => (
                      <tr key={i} className="border-b border-iv-border/50 hover:bg-iv-surface/50">
                        <td className="px-4 py-3 text-iv-text">{formatDate(m.captured_at)}</td>
                        <td className="px-4 py-3 text-iv-text">{m.mileage_in_km != null ? `${m.mileage_in_km.toLocaleString()} km` : "—"}</td>
                        <td className="px-4 py-3 text-iv-warning">{m.inspection_due_in_days != null ? `${m.inspection_due_in_days}d / ${m.inspection_due_in_km?.toLocaleString() || "—"} km` : "—"}</td>
                        <td className="px-4 py-3 text-iv-text">{m.oil_service_due_in_days != null ? `${m.oil_service_due_in_days}d` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ===== COMMANDS ===== */}
      {tab === "commands" && (
        <div className="space-y-4">
          {cmdResult && <CommandResult status={cmdResult.status} message={cmdResult.message} />}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <div className="glass rounded-xl p-4 flex flex-col items-center gap-3 col-span-2 lg:col-span-1">
              <Thermometer size={24} className="text-iv-green" />
              <span className="text-xs font-medium text-iv-text">Start Climate</span>
              <div className="flex items-center gap-2 w-full">
                <input type="number" min="16" max="30" value={climateTemp} onChange={(e) => setClimateTemp(e.target.value)}
                  className="w-full rounded-lg bg-iv-surface border border-iv-border px-3 py-1.5 text-sm text-iv-text text-center focus:outline-none focus:border-iv-green/50" />
                <span className="text-xs text-iv-muted">°C</span>
              </div>
              <button onClick={() => runCommand("climatization/start", { target_temperature: parseFloat(climateTemp) })}
                disabled={cmdLoading !== null}
                className="w-full rounded-lg bg-iv-green/15 px-3 py-1.5 text-xs font-medium text-iv-green transition-colors hover:bg-iv-green/25 disabled:opacity-50">
                {cmdLoading === "climatization/start" ? "Sending..." : "Start"}
              </button>
            </div>
            <CommandButton icon={ThermometerSnowflake} label="Stop Climate" onClick={() => runCommand("climatization/stop")} loading={cmdLoading === "climatization/stop"} />
            <CommandButton icon={Zap} label="Start Charging" onClick={() => runCommand("charging/start")} loading={cmdLoading === "charging/start"} />
            <CommandButton icon={ZapOff} label="Stop Charging" onClick={() => runCommand("charging/stop")} loading={cmdLoading === "charging/stop"} />
            <CommandButton icon={Lock} label="Lock" onClick={() => runCommand("lock")} loading={cmdLoading === "lock"} />
            <div className="glass rounded-xl p-4 flex flex-col items-center gap-3 col-span-2 lg:col-span-1">
              <Unlock size={24} className="text-iv-warning" />
              <span className="text-xs font-medium text-iv-text">Unlock</span>
              <input type="password" placeholder="SPIN" value={unlockSpin} onChange={(e) => setUnlockSpin(e.target.value)}
                className="w-full rounded-lg bg-iv-surface border border-iv-border px-3 py-1.5 text-sm text-iv-text text-center focus:outline-none focus:border-iv-green/50" />
              <button onClick={() => runCommand("unlock", { spin: unlockSpin })} disabled={cmdLoading !== null || !unlockSpin}
                className="w-full rounded-lg bg-iv-warning/15 px-3 py-1.5 text-xs font-medium text-iv-warning transition-colors hover:bg-iv-warning/25 disabled:opacity-50">
                {cmdLoading === "unlock" ? "Sending..." : "Unlock"}
              </button>
            </div>
            <CommandButton icon={Volume2} label="Honk & Flash" onClick={() => runCommand("honk-flash")} loading={cmdLoading === "honk-flash"} />
            <CommandButton icon={Power} label="Wake" onClick={() => runCommand("wake")} loading={cmdLoading === "wake"} />
          </div>
        </div>
      )}

      {/* Delete confirmation modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowDeleteModal(false)} />
          <div className="glass relative w-full max-w-sm rounded-2xl p-6">
            <h2 className="text-lg font-semibold text-iv-text mb-2">Delete Vehicle</h2>
            <p className="text-sm text-iv-muted mb-6">
              Are you sure? All collected data for <strong className="text-iv-text">{vehicle.display_name || vehicle.model}</strong> will be permanently removed.
            </p>
            <div className="flex gap-3">
              <button onClick={() => setShowDeleteModal(false)}
                className="flex-1 rounded-xl border border-iv-border px-4 py-2.5 text-sm font-medium text-iv-muted transition-colors hover:bg-iv-surface hover:text-iv-text">
                Cancel
              </button>
              <button onClick={handleDelete} disabled={deleteLoading}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-iv-danger px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-iv-danger/90 disabled:opacity-50">
                {deleteLoading ? <Loader2 size={16} className="animate-spin" /> : null}
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatusRow({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5 border-b border-iv-border/30 last:border-0">
      <span className="text-xs text-iv-muted shrink-0 pt-0.5">{label}</span>
      <span className={`text-xs font-medium text-right ${ok === true ? "text-iv-green" : ok === false ? "text-iv-warning" : "text-iv-text"}`}>
        {value}
      </span>
    </div>
  );
}
