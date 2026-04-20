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
  Leaf as LeafyGreenIcon,
  Euro as EuroIcon,
  Wallet as WalletIcon,
  BatteryCharging as BatteryChargingIcon,
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
  ReferenceLine,
} from "recharts";
import { api } from "@/lib/api";
import { DateRangePicker, type DateRangeValue } from "@/components/ui/DateRangePicker";
import { subDays, startOfDay, endOfDay } from "date-fns";
import dynamic from "next/dynamic";

import { CarOverviewDashboard } from "@/components/statistics/CarOverviewDashboard";
import { ChargingSessionsDashboard } from "@/components/statistics/ChargingSessionsDashboard";
import { ChargingStatisticsDashboard } from "@/components/statistics/ChargingStatisticsDashboard";
import { DrivingStatisticsDashboard } from "@/components/statistics/DrivingStatisticsDashboard";
import { LocationsDashboard } from "@/components/statistics/LocationsDashboard";
import { VisitedDashboard } from "@/components/statistics/VisitedDashboard";
import { MileageKMDashboard } from "@/components/statistics/MileageKMDashboard";
import { TripsDashboard } from "@/components/statistics/TripsDashboard";
import { VehicleCarousel } from "@/components/vehicle/VehicleCarousel";

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
interface AdvancedAnalytics {
  efficiency: {
    avg_kwh_100km: number;
    cold_penalty_pct: number;
    cold_eff_kwh_100km: number;
    warm_eff_kwh_100km: number;
  };
  trip_types: {
    short_pct: number;
    medium_pct: number;
    long_pct: number;
  };
  phantom_drain: {
    pct_per_day: number;
  };
  energy_prices?: {
    country_code: string;
    electricity_eur_kwh: number;
    petrol_eur_l: number;
    user_avg_electricity_eur_kwh?: number | null;
  };
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
  return new Date(ts).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
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
      className={`relative group h-32 w-full rounded-2xl p-4 flex flex-col items-start justify-between transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed border backdrop-blur-md shadow-sm overflow-hidden ${
        variant === "danger" 
          ? "bg-iv-danger/5 border-iv-danger/20 hover:bg-iv-danger/10 hover:border-iv-danger/30" 
          : "bg-iv-surface/60 border-iv-border/50 hover:bg-iv-surface hover:border-iv-border"
      }`}>
      
      {/* Background Gradient Blob for visual interest */}
      <div className={`absolute -right-4 -top-4 h-16 w-16 rounded-full blur-2xl transition-opacity duration-500 opacity-0 group-hover:opacity-20 ${
        variant === "danger" ? "bg-iv-danger" : "bg-iv-green"
      }`} />

      {/* Icon Area */}
      <div className={`p-2.5 rounded-full transition-colors ${
        variant === "danger" 
          ? "bg-iv-danger/10 text-iv-danger group-hover:bg-iv-danger group-hover:text-white" 
          : "bg-iv-text/5 text-iv-text group-hover:bg-iv-text group-hover:text-iv-black"
      }`}>
        {loading ? <Loader2 size={20} className="animate-spin" /> : <Icon size={20} />}
      </div>

      {/* Label */}
      <span className={`text-sm font-semibold tracking-tight ${
        variant === "danger" ? "text-iv-danger" : "text-iv-text"
      }`}>
        {label}
      </span>
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
  const [advancedAnalytics, setAdvancedAnalytics] = useState<AdvancedAnalytics | null>(null);
  const [statPeriod, setStatPeriod] = useState<"day" | "week" | "month" | "year">("day");
  const [maintenanceDateRange, setMaintenanceDateRange] = useState<DateRangeValue>({
    from: startOfDay(subDays(new Date(), 90)),
    to: endOfDay(new Date()),
  });
  

  const [refreshLoading, setRefreshLoading] = useState(false);
  const [refreshToast, setRefreshToast] = useState<{ status: "success" | "error"; message: string } | null>(null);

  const [cmdLoading, setCmdLoading] = useState<string | null>(null);
  const [cmdResult, setCmdResult] = useState<{ status: "success" | "error"; message: string } | null>(null);
  const [climateTemp, setClimateTemp] = useState("21");
  const [unlockSpin, setUnlockSpin] = useState("");
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const [visibleTabs, setVisibleTabs] = useState(tabs);

  useEffect(() => {
     // Check settings preference for commands
     const showCmds = localStorage.getItem("ivdrive_show_commands") === "true";
     if (!showCmds) {
       setVisibleTabs(tabs.filter(t => t.key !== "commands"));
       // If currently on commands tab but it's disabled, switch to overview
       if (tab === "commands") setTab("overview");
     } else {
       setVisibleTabs(tabs);
     }
  }, [tab]);

  const loadData = useCallback(async () => {
    try {
      const results = await Promise.allSettled([
        api.getVehicle(vehicleId), 
        api.getVehicleStatus(vehicleId),
        api.getAdvancedAnalyticsOverview(vehicleId)
      ]);
      
      if (results[0].status === 'fulfilled') setVehicle(results[0].value);
      if (results[1].status === 'fulfilled') setStatus(results[1].value);
      if (results[2].status === 'fulfilled') setAdvancedAnalytics(results[2].value);

      // Essential data: if getVehicle fails, we can't show the page
      if (results[0].status === 'rejected') router.replace("/");
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
      // Fetch raw data for client-side aggregation (Helicopter View)
      Promise.all([
        api.getTrips(vehicleId, 100),
        api.getChargingSessions(vehicleId, 100)
      ]).then(([t, s]) => {
        setTrips(t);
        setSessions(s);
      });
    } else if (tab === "maintenance") {
      // Calculate 90 days ago
      const d = new Date();
      d.setDate(d.getDate() - 90);
      const fromStr = d.toISOString();
      
      // Fetch data starting from 90 days ago
      Promise.all([
        api.getMaintenance(vehicleId, 10000, fromStr), 
        api.getOdometer(vehicleId, 10000, fromStr)
      ])
        .then(([m, o]) => { 
          // Deduplicate to latest record per day
          const filterByDay = <T extends { captured_at: string }>(items: T[]) => {
            const latestByDay = new Map<string, T>();
            
            items.forEach(item => {
              const date = new Date(item.captured_at);
              // Use local date string to group by day correctly
              const dayKey = date.toLocaleDateString();
              
              // If we haven't seen this day, or this item is newer than what we have
              if (!latestByDay.has(dayKey) || new Date(item.captured_at) > new Date(latestByDay.get(dayKey)!.captured_at)) {
                latestByDay.set(dayKey, item);
              }
            });

            // Return values sorted by date descending (newest first)
            return Array.from(latestByDay.values()).sort((a, b) => 
              new Date(b.captured_at).getTime() - new Date(a.captured_at).getTime()
            );
          };

          setMaintenance(filterByDay(m)); 
          setOdometer(filterByDay(o)); 
        });
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
        {visibleTabs.map((t) => (
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
                <StatusRow label="Doors" value={status.doors_open || "CLOSED"} ok={status.doors_open === "CLOSED" || !status.doors_open} />
                <StatusRow label="Windows" value={status.windows_open || "CLOSED"} ok={status.windows_open === "CLOSED" || !status.windows_open} />
                <StatusRow label="Trunk" value={status.trunk_open ? "OPEN" : "CLOSED"} ok={!status.trunk_open} />
                <StatusRow label="Bonnet" value={status.bonnet_open ? "OPEN" : "CLOSED"} ok={!status.bonnet_open} />
                <StatusRow label="Lights" value={status.lights_on || "OFF"} ok={status.lights_on === "OFF" || !status.lights_on} />
                <StatusRow label="Motion" value={status.is_in_motion ? "MOVING" : "PARKED"} ok={!status.is_in_motion} />
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
              <VehicleCarousel renders={vehicle.specifications.renders} />
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

      {tab === "trips" && (() => {
        const to = new Date();
        const from = new Date(to.getTime() - 30 * 24 * 60 * 60 * 1000);
        return <TripsDashboard vehicleId={vehicleId} dateRange={{ from, to }} />;
      })()}

      {/* ===== STATISTICS (Helicopter View) ===== */}
      {/* ===== STATISTICS (Helicopter View) ===== */}
      {tab === "statistics" && (() => {
        const now = new Date();
        const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
        
        const recentTrips = trips.filter(t => new Date(t.start_date) >= thirtyDaysAgo);
        const recentSessions = sessions.filter(s => new Date(s.session_start) >= thirtyDaysAgo);

        const totalKm = recentTrips.reduce((acc, t) => acc + ((t as any).distance_km ?? (t.end_odometer && t.start_odometer ? t.end_odometer - t.start_odometer : 0)), 0);
        const totalChargedKwh = recentSessions.reduce((acc, s) => acc + (s.energy_kwh || 0), 0);
        
        const acCount = recentSessions.filter(s => s.charging_type === "AC").length;
        const totalSessionsCount = recentSessions.length;
        const acPercent = totalSessionsCount > 0 ? Math.round((acCount / totalSessionsCount) * 100) : 0;
        const dcPercent = totalSessionsCount > 0 ? 100 - acPercent : 0;

        const totalActualCost = recentSessions.reduce((acc, s) => acc + ((s as any).actual_cost_eur || 0), 0);
        const finalCostPerKwh = totalChargedKwh > 0 ? totalActualCost / totalChargedKwh : 0.25;

        const analytics = advancedAnalytics || {
          efficiency: { avg_kwh_100km: 18.5, cold_penalty_pct: 15, cold_eff_kwh_100km: 22.5, warm_eff_kwh_100km: 16.2 },
          trip_types: { short_pct: 0, medium_pct: 0, long_pct: 0 },
          phantom_drain: { pct_per_day: 1.2 },
          energy_prices: { country_code: "LT", electricity_eur_kwh: 0.25, petrol_eur_l: 1.65 }
        };

        const activeElecPrice = analytics.energy_prices?.electricity_eur_kwh || 0.25;
        const activePetrolPrice = analytics.energy_prices?.petrol_eur_l || 1.65;
        const activeCountry = analytics.energy_prices?.country_code || "LT";
        const userAvgElecPrice = analytics.energy_prices?.user_avg_electricity_eur_kwh;
        
        // Cost is calculated using real energy prices from our backend
        const estTotalCost = (totalKm / 100) * analytics.efficiency.avg_kwh_100km * activeElecPrice;
        const costPer100km = analytics.efficiency.avg_kwh_100km * activeElecPrice;
        
        const realTotalCost = userAvgElecPrice ? (totalKm / 100) * analytics.efficiency.avg_kwh_100km * userAvgElecPrice : null;

        return (
          <div className="space-y-6">
            <h2 className="text-xl font-bold text-iv-text flex items-center gap-2">
              <BarChart3 className="w-6 h-6 text-iv-cyan" />
              Advanced Analytics (30 Days)
            </h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              
              <div className="glass p-5 rounded-2xl border border-iv-border relative overflow-hidden group">
                <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                  <TrendingUp size={80} className="text-iv-green" />
                </div>
                <h3 className="text-sm font-medium text-iv-muted flex items-center gap-2 mb-1">
                  <LeafyGreenIcon className="text-iv-green" size={16} /> Efficiency
                </h3>
                <div className="flex items-baseline gap-2 mt-2">
                  <span className="text-3xl font-bold text-iv-text">{analytics.efficiency.avg_kwh_100km.toFixed(1)}</span>
                  <span className="text-sm text-iv-muted">kWh/100km</span>
                </div>
                <div className="mt-3 flex items-center gap-2 text-xs font-medium text-iv-muted">
                   <span>Real-world average</span>
                </div>
              </div>

              <div className="glass p-5 rounded-2xl border border-iv-border relative overflow-hidden group">
                <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                  <BatteryChargingIcon size={80} className="text-iv-cyan" />
                </div>
                <h3 className="text-sm font-medium text-iv-muted flex items-center gap-2 mb-1">
                  <Zap size={16} className="text-iv-cyan" /> Charging Mix
                </h3>
                <div className="flex items-center gap-4 mt-3">
                  <div className="relative h-12 w-12 rounded-full border-4 border-iv-cyan" 
                       style={{ borderColor: `conic-gradient(var(--iv-cyan) ${acPercent}%, var(--iv-warning) 0)` }}>
                    <svg viewBox="0 0 36 36" className="h-full w-full -rotate-90">
                      <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="var(--iv-warning)" strokeWidth="4" />
                      <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="var(--iv-cyan)" strokeWidth="4" strokeDasharray={`${acPercent}, 100`} />
                    </svg>
                    <div className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-iv-text">{totalSessionsCount}</div>
                  </div>
                  <div>
                    <div className="flex items-center gap-2 text-sm">
                      <span className="w-2 h-2 rounded-full bg-iv-cyan"></span>
                      <span className="font-semibold text-iv-text">{acPercent}% AC</span>
                    </div>
                    <div className="flex items-center gap-2 text-sm mt-1">
                      <span className="w-2 h-2 rounded-full bg-iv-warning"></span>
                      <span className="font-semibold text-iv-text">{dcPercent}% DC</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="glass p-5 rounded-2xl border border-iv-border relative overflow-hidden group">
                 <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                  <EuroIcon size={80} className="text-iv-text" />
                </div>
                <h3 className="text-sm font-medium text-iv-muted flex items-center gap-2 mb-1">
                  <WalletIcon size={16} className="text-iv-text" /> Running Cost
                </h3>
                {realTotalCost !== null ? (
                  <>
                    <div className="flex items-baseline gap-2 mt-2">
                      <span className="text-2xl font-bold text-iv-muted line-through opacity-70">€{estTotalCost.toFixed(0)}</span>
                      <span className="text-3xl font-bold text-iv-text">€{realTotalCost.toFixed(0)}</span>
                      <span className="text-sm text-iv-muted">est. total</span>
                    </div>
                    <div className="mt-3 text-xs font-medium text-iv-muted">
                      ~ <span className="text-iv-text font-semibold">€{(analytics.efficiency.avg_kwh_100km * userAvgElecPrice!).toFixed(2)}</span> / 100km
                    </div>
                    <div className="mt-1 text-[10px] text-iv-muted opacity-60">
                      Based on your actual avg €{userAvgElecPrice!.toFixed(2)}/kWh (vs {activeCountry} avg €{activeElecPrice.toFixed(2)})
                    </div>
                  </>
                ) : (
                  <>
                    <div className="flex items-baseline gap-2 mt-2">
                      <span className="text-3xl font-bold text-iv-text">€{estTotalCost.toFixed(0)}</span>
                      <span className="text-sm text-iv-muted">est. total</span>
                    </div>
                    <div className="mt-3 text-xs font-medium text-iv-muted">
                      ~ <span className="text-iv-text font-semibold">€{costPer100km.toFixed(2)}</span> / 100km
                    </div>
                    <div className="mt-1 text-[10px] text-iv-muted opacity-60">
                      Based on {activeCountry} avg €{activeElecPrice.toFixed(2)}/kWh
                    </div>
                  </>
                )}
              </div>

              <div className="glass p-5 rounded-2xl border border-iv-border relative overflow-hidden group">
                 <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                  <ThermometerSnowflake size={80} className="text-iv-cyan" />
                </div>
                <h3 className="text-sm font-medium text-iv-muted flex items-center gap-2 mb-1">
                  <Thermometer size={16} className="text-iv-cyan" /> Cold Weather Impact
                </h3>
                <div className="flex items-baseline gap-2 mt-2">
                  <span className="text-3xl font-bold text-iv-warning">+{analytics.efficiency.cold_penalty_pct}%</span>
                  <span className="text-sm text-iv-muted">consumption</span>
                </div>
                <div className="mt-3 flex flex-col gap-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-iv-muted">Cold (&lt;7°C)</span>
                    <span className="font-mono text-iv-text">{analytics.efficiency.cold_eff_kwh_100km.toFixed(1)} kWh/100km</span>
                  </div>
                   <div className="flex justify-between">
                    <span className="text-iv-muted">Warm (&gt;12°C)</span>
                    <span className="font-mono text-iv-text">{analytics.efficiency.warm_eff_kwh_100km.toFixed(1)} kWh/100km</span>
                  </div>
                </div>
              </div>

               <div className="glass p-5 rounded-2xl border border-iv-border relative overflow-hidden group">
                 <h3 className="text-sm font-medium text-iv-muted flex items-center gap-2 mb-3">
                  <MapPin size={16} className="text-iv-text" /> Trip Types
                </h3>
                <div className="space-y-3">
                   <div>
                     <div className="flex justify-between text-xs mb-1">
                       <span className="text-iv-muted">Short / City (&lt;15km)</span>
                       <span className="text-iv-text font-mono">{analytics.trip_types.short_pct}%</span>
                     </div>
                     <div className="h-1.5 w-full bg-iv-surface rounded-full overflow-hidden">
                       <div className="h-full bg-iv-cyan" style={{ width: `${analytics.trip_types.short_pct}%` }} />
                     </div>
                   </div>
                   <div>
                     <div className="flex justify-between text-xs mb-1">
                       <span className="text-iv-muted">Commute (15-80km)</span>
                       <span className="text-iv-text font-mono">{analytics.trip_types.medium_pct}%</span>
                     </div>
                     <div className="h-1.5 w-full bg-iv-surface rounded-full overflow-hidden">
                       <div className="h-full bg-iv-green" style={{ width: `${analytics.trip_types.medium_pct}%` }} />
                     </div>
                   </div>
                   <div>
                     <div className="flex justify-between text-xs mb-1">
                       <span className="text-iv-muted">Long Haul (&gt;80km)</span>
                       <span className="text-iv-text font-mono">{analytics.trip_types.long_pct}%</span>
                     </div>
                     <div className="h-1.5 w-full bg-iv-surface rounded-full overflow-hidden">
                       <div className="h-full bg-iv-warning" style={{ width: `${analytics.trip_types.long_pct}%` }} />
                     </div>
                   </div>
                </div>
              </div>

              <div className="glass p-5 rounded-2xl border border-iv-border relative overflow-hidden group">
                 <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                  <ZapOff size={80} className="text-iv-text" />
                </div>
                <h3 className="text-sm font-medium text-iv-muted flex items-center gap-2 mb-1">
                  <ZapOff size={16} className="text-iv-text" /> Phantom Drain
                </h3>
                <div className="flex items-baseline gap-2 mt-2">
                  <span className="text-3xl font-bold text-iv-text">{analytics.phantom_drain.pct_per_day.toFixed(1)}</span>
                  <span className="text-sm text-iv-muted">% / day</span>
                </div>
                <div className="mt-3 text-[10px] text-iv-muted">Real-world standby loss</div>
                <div className="mt-1 text-[10px] text-iv-green flex items-center gap-1">
                   <CheckCircle2 size={10} /> Calculation Active
                </div>
              </div>

              <div className="glass p-5 rounded-2xl border border-iv-border relative overflow-hidden group">
                <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                  <Plug size={80} className="text-iv-green" />
                </div>
                <h3 className="text-sm font-medium text-iv-muted flex items-center gap-2 mb-1">
                  <Plug size={16} className="text-iv-green" /> Total Energy Added
                </h3>
                 <div className="flex items-baseline gap-2 mt-2">
                  <span className="text-3xl font-bold text-iv-text">{totalChargedKwh.toFixed(1)}</span>
                  <span className="text-sm text-iv-muted">kWh</span>
                </div>
                <div className="mt-3 flex flex-col gap-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-iv-muted">Avg / Session</span>
                    <span className="font-mono text-iv-text">{(totalChargedKwh / (totalSessionsCount || 1)).toFixed(1)} kWh</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-iv-muted">Equivalent</span>
                    <span className="font-mono text-iv-text">~{(totalChargedKwh / 77).toFixed(1)} full charges</span>
                  </div>
                </div>
              </div>

              <div className="glass p-5 rounded-2xl border border-iv-border relative overflow-hidden group">
                 <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                  <LeafyGreenIcon size={80} className="text-iv-green" />
                </div>
                <h3 className="text-sm font-medium text-iv-muted flex items-center gap-2 mb-1">
                  <LeafyGreenIcon size={16} className="text-iv-green" /> Savings vs Gas
                </h3>
                {(() => {
                   const ICE_CONSUMPTION = 8.0; // 8 L/100km for comparable SUV
                   const dieselCostPer100 = ICE_CONSUMPTION * activePetrolPrice;
                   const effCostPer100km = userAvgElecPrice ? analytics.efficiency.avg_kwh_100km * userAvgElecPrice : costPer100km;
                   const savingsPer100 = Math.max(0, dieselCostPer100 - effCostPer100km);
                   const totalSavings = (totalKm / 100) * savingsPer100;
                   
                    return (
                    <>
                      <div className="flex items-baseline gap-2 mt-2">
                        <span className="text-3xl font-bold text-iv-green">~€{totalSavings.toFixed(0)}</span>
                        <span className="text-sm text-iv-muted">saved</span>
                      </div>
                      <div className="mt-3 text-xs font-medium text-iv-muted">vs {ICE_CONSUMPTION}L/100km SUV</div>
                      <div className="mt-1 text-[10px] text-iv-muted opacity-60">
                        Gas: €{dieselCostPer100.toFixed(2)}/100km | EV: €{effCostPer100km.toFixed(2)}/100km
                      </div>
                    </>
                   );
                })()}
              </div>

            </div>
          </div>
        );
      })()}

      {/* ===== MAINTENANCE ===== */}


      {tab === "maintenance" && (
        <div className="space-y-4">
          <div className="glass rounded-xl p-5">
              <h2 className="text-xl font-bold text-iv-text flex items-center gap-2">
                <Wrench className="w-5 h-5 text-iv-cyan" />
                Maintenance & Odometer
              </h2>
              <p className="text-sm text-iv-muted">Track mileage and upcoming service intervals (Last 90 Days)</p>
          </div>

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
                  <AreaChart data={(() => {
                    const data = odometer.slice().reverse().map(o => ({
                      time: new Date(o.captured_at).getTime(),
                      km: o.mileage_in_km,
                    }));
                    
                    if (maintenance.length > 0 && maintenance[0].inspection_due_in_days != null && maintenance[0].inspection_due_in_days < 0) {
                       const dueDate = new Date();
                       dueDate.setDate(dueDate.getDate() + maintenance[0].inspection_due_in_days);
                       const dueTime = dueDate.getTime();
                       
                       if (data.length > 0 && dueTime < data[0].time) {
                          data.unshift({ time: dueTime, km: null as any });
                       }
                    }
                    return data;
                  })()}>
                    <defs>
                      {/* Stroke Gradient (Solid Color) */}
                      <linearGradient id="mileageStroke" x1="0" y1="0" x2="1" y2="0">
                        {(() => {
                           if (!maintenance.length || maintenance[0].inspection_due_in_days == null) return <stop offset="100%" stopColor="#4BA82E" />;
                           const data = odometer.slice().reverse();
                           if (!data.length) return <stop offset="100%" stopColor="#4BA82E" />;
                           
                           const startTime = new Date(data[0].captured_at).getTime();
                           const endTime = new Date(data[data.length - 1].captured_at).getTime();
                           const dueDate = new Date();
                           dueDate.setDate(dueDate.getDate() + maintenance[0].inspection_due_in_days);
                           const dueTime = dueDate.getTime();

                           if (dueTime <= startTime) {
                             return (
                               <>
                                 <stop offset="0%" stopColor="#ef4444" />
                                 <stop offset="100%" stopColor="#b91c1c" /> 
                               </>
                             );
                           }
                           if (dueTime >= endTime) return <stop offset="100%" stopColor="#4BA82E" />;

                           const totalDuration = endTime - startTime;
                           const offset = (dueTime - startTime) / totalDuration;
                           const offsetPct = `${Math.max(0, Math.min(100, offset * 100))}%`;

                           return (
                             <>
                               <stop offset="0%" stopColor="#4BA82E" />
                               <stop offset={offsetPct} stopColor="#ef4444" />
                               <stop offset="100%" stopColor="#b91c1c" />
                             </>
                           );
                        })()}
                      </linearGradient>

                      {/* Fill Gradient (Low Opacity) */}
                      <linearGradient id="mileageFill" x1="0" y1="0" x2="1" y2="0">
                        {(() => {
                           if (!maintenance.length || maintenance[0].inspection_due_in_days == null) return <stop offset="100%" stopColor="#4BA82E" stopOpacity={0.2} />;
                           const data = odometer.slice().reverse();
                           if (!data.length) return <stop offset="100%" stopColor="#4BA82E" stopOpacity={0.2} />;
                           
                           const startTime = new Date(data[0].captured_at).getTime();
                           const endTime = new Date(data[data.length - 1].captured_at).getTime();
                           const dueDate = new Date();
                           dueDate.setDate(dueDate.getDate() + maintenance[0].inspection_due_in_days);
                           const dueTime = dueDate.getTime();

                           if (dueTime <= startTime) {
                             return (
                               <>
                                 <stop offset="0%" stopColor="#ef4444" stopOpacity={0.3} />
                                 <stop offset="100%" stopColor="#b91c1c" stopOpacity={0.3} /> 
                               </>
                             );
                           }
                           if (dueTime >= endTime) return <stop offset="100%" stopColor="#4BA82E" stopOpacity={0.2} />;

                           const totalDuration = endTime - startTime;
                           const offset = (dueTime - startTime) / totalDuration;
                           const offsetPct = `${Math.max(0, Math.min(100, offset * 100))}%`;

                           return (
                             <>
                               <stop offset="0%" stopColor="#4BA82E" stopOpacity={0.2} />
                               <stop offset={offsetPct} stopColor="#ef4444" stopOpacity={0.3} />
                               <stop offset="100%" stopColor="#b91c1c" stopOpacity={0.4} />
                             </>
                           );
                        })()}
                      </linearGradient>
                    </defs>
                    <XAxis 
                      dataKey="time" 
                      type="number" 
                      domain={['dataMin', 'dataMax']} 
                      scale="time" 
                      tickFormatter={(ts) => new Date(ts).toLocaleDateString([], { month: "short", day: "numeric" })}
                      stroke="#8b8fa3" 
                      fontSize={11} 
                      tickLine={false} 
                      axisLine={false} 
                    />
                    <YAxis 
                      stroke="#8b8fa3" 
                      fontSize={11} 
                      tickLine={false} 
                      axisLine={false} 
                      domain={['dataMin - 100', 'auto']}
                      tickFormatter={v => `${(v / 1000).toFixed(1)}k`} 
                    />
                    <Tooltip 
                      content={({ active, payload, label }) => {
                        if (!active || !payload?.length) return null;
                        return (
                          <div className="rounded-lg bg-iv-charcoal border border-iv-border px-3 py-2 shadow-xl">
                            <p className="text-xs text-iv-muted">
                              {new Date(label).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}
                            </p>
                            <p className="text-sm font-semibold text-iv-text">
                              {Number(payload[0].value).toLocaleString()} km
                            </p>
                          </div>
                        );
                      }}
                    />
                    <Area 
                        type="monotone" 
                        dataKey="km" 
                        stroke="url(#mileageStroke)" 
                        fill="url(#mileageFill)" 
                        strokeWidth={2} 
                        connectNulls 
                    />
                    {maintenance.length > 0 && maintenance[0].inspection_due_in_days != null && maintenance[0].inspection_due_in_days < 0 && (
                      <ReferenceLine 
                        x={new Date().getTime() + (maintenance[0].inspection_due_in_days * 24 * 60 * 60 * 1000)} 
                        stroke="#ef4444" 
                        strokeDasharray="4 4"
                        isFront={true}
                        label={{ 
                          value: "INSPECTION DUE", 
                          position: "insideTopLeft", 
                          fill: "#ef4444", 
                          fontSize: 10,
                          fontWeight: "bold",
                          offset: 10
                        }} 
                      />
                    )}
                  </AreaChart>
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
        <div className="space-y-6">
          {cmdResult && <CommandResult status={cmdResult.status} message={cmdResult.message} />}
          
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            
            {/* Climate Control - Double Height/Width on mobile, square on desktop */}
            <div className="col-span-2 lg:col-span-2 row-span-1 lg:row-span-1 relative overflow-hidden rounded-2xl bg-iv-surface/40 border border-iv-border/50 backdrop-blur-md p-5 flex flex-col justify-between group hover:border-iv-green/30 transition-all">
               <div className="flex justify-between items-start">
                 <div className="p-2.5 rounded-full bg-iv-green/10 text-iv-green">
                   <Thermometer size={20} />
                 </div>
                 <div className="flex items-center gap-1 bg-iv-surface rounded-lg px-2 py-1 border border-iv-border/50">
                    <input type="number" min="16" max="30" value={climateTemp} onChange={(e) => setClimateTemp(e.target.value)}
                      className="w-8 bg-transparent text-center font-bold text-lg text-iv-text focus:outline-none" />
                    <span className="text-xs text-iv-muted">°C</span>
                 </div>
               </div>
               
               <div>
                 <h3 className="font-semibold text-iv-text">Climate Control</h3>
                 <div className="flex gap-2 mt-3">
                    <button onClick={() => runCommand("climatization/start", { target_temperature: parseFloat(climateTemp) })}
                      disabled={cmdLoading !== null}
                      className="flex-1 py-2.5 rounded-xl bg-iv-text text-iv-black font-semibold text-sm hover:bg-iv-text/90 transition-colors disabled:opacity-50">
                      {cmdLoading === "climatization/start" ? "Starting..." : "Start"}
                    </button>
                    <button onClick={() => runCommand("climatization/stop")}
                      disabled={cmdLoading !== null}
                      className="px-4 py-2.5 rounded-xl bg-iv-surface border border-iv-border text-iv-text font-medium text-sm hover:bg-iv-border/50 transition-colors">
                      Stop
                    </button>
                 </div>
               </div>
            </div>

            {/* Unlock - Double Height/Width on mobile, square on desktop */}
            <div className="col-span-2 lg:col-span-2 row-span-1 relative overflow-hidden rounded-2xl bg-iv-surface/40 border border-iv-border/50 backdrop-blur-md p-5 flex flex-col justify-between group hover:border-iv-warning/30 transition-all">
               <div className="flex justify-between items-start">
                 <div className="p-2.5 rounded-full bg-iv-warning/10 text-iv-warning">
                   <Unlock size={20} />
                 </div>
               </div>
               
               <div>
                 <h3 className="font-semibold text-iv-text">Security Unlock</h3>
                 <div className="flex gap-2 mt-3">
                    <input type="password" placeholder="S-PIN" value={unlockSpin} onChange={(e) => setUnlockSpin(e.target.value)}
                      className="flex-1 rounded-xl bg-iv-surface border border-iv-border px-3 text-sm text-iv-text text-center focus:outline-none focus:border-iv-warning/50 transition-all" />
                    <button onClick={() => runCommand("unlock", { spin: unlockSpin })} disabled={cmdLoading !== null || !unlockSpin}
                      className="px-6 py-2.5 rounded-xl bg-iv-warning/10 text-iv-warning border border-iv-warning/20 font-semibold text-sm hover:bg-iv-warning/20 transition-colors disabled:opacity-50">
                      {cmdLoading === "unlock" ? "..." : "Unlock"}
                    </button>
                 </div>
               </div>
            </div>

            <CommandButton icon={Zap} label="Start Charging" onClick={() => runCommand("charging/start")} loading={cmdLoading === "charging/start"} />
            <CommandButton icon={ZapOff} label="Stop Charging" onClick={() => runCommand("charging/stop")} loading={cmdLoading === "charging/stop"} />
            <CommandButton icon={Lock} label="Lock Vehicle" onClick={() => runCommand("lock")} loading={cmdLoading === "lock"} />
            <CommandButton icon={Volume2} label="Honk & Flash" onClick={() => runCommand("honk-flash")} loading={cmdLoading === "honk-flash"} />
            <CommandButton icon={Power} label="Wake Up" onClick={() => runCommand("wake")} loading={cmdLoading === "wake"} />
            
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
