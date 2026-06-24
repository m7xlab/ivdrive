"use client";
import Link from "next/link";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Battery,
  MapPin,
  Clock,
  Trash2,
  Loader2,
  Wifi,
  WifiOff,
  Lock,
  LockOpen,
  Gauge,
  Zap,
  ChevronRight,
} from "lucide-react";

import { DataHealthBadge } from "@/components/vehicle/data-health-badge";

interface VehicleStatus {
  vin_last4?: string;
  display_name?: string;
  manufacturer?: string;
  model?: string;
  image_url?: string | null;
  latest_battery_level: number | null;
  latest_range_km: number | null;
  latest_charging_state: string | null;
  latest_vehicle_state: string | null;
  latest_position: { latitude: number; longitude: number } | null;
  last_updated: string | null;
  is_online?: boolean | null;
  doors_locked?: string | null;
  connector_status?: string | null;
  odometer_km?: number | null;
  model_year?: string | null;
}

interface VehicleCardProps {
  vehicleId: string;
  displayName?: string;
  manufacturer?: string;
  model?: string;
  modelYear?: string | null;
  imageUrl?: string | null;
  connectorStatus?: string | null;
  status: VehicleStatus | null;
  loading?: boolean;
  onDelete?: (id: string) => void | Promise<void>;
  onAfterRefresh?: () => void;
}

function BatteryIndicator({ percentage }: { percentage: number }) {
  const color =
    percentage > 60 ? "text-iv-green" : percentage > 20 ? "text-iv-warning" : "text-iv-danger";
  const bgColor =
    percentage > 60 ? "bg-iv-green" : percentage > 20 ? "bg-iv-warning" : "bg-iv-danger";

  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-1.5">
        <Battery size={18} className={color} />
        <span className="text-xs text-iv-muted">Battery</span>
      </div>
      <div className="flex-1 flex items-center gap-2">
        <div className="flex-1 h-2 rounded-full bg-iv-surface overflow-hidden">
          <div
            className={`h-full rounded-full ${bgColor} transition-all duration-1000 ease-out`}
            style={{ width: `${Math.min(100, Math.max(0, percentage))}%` }}
          />
        </div>
        <span className={`text-sm font-semibold tabular-nums ${color}`}>
          {Math.round(percentage)}%
        </span>
      </div>
    </div>
  );
}

function ConnectorDot({ status }: { status: string | null | undefined }) {
  if (!status) return null;
  const colorMap: Record<string, string> = {
    active: "bg-iv-green",
    pending: "bg-iv-warning",
    auth_failed: "bg-iv-danger",
    token_error: "bg-iv-danger",
  };
  const color = colorMap[status] || "bg-iv-muted";
  const label =
    status === "active"
      ? "Connected"
      : status === "pending"
        ? "Pending"
        : status === "auth_failed"
          ? "Auth Failed"
          : status === "token_error"
            ? "Token Error"
            : status;

  return (
    <span className="flex items-center gap-1.5" title={label}>
      <span className={`h-2 w-2 rounded-full ${color}`} />
    </span>
  );
}

function formatTimeAgo(dateStr: string | null): string {
  if (!dateStr) return "Never";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function CardSkeleton() {
  return (
    <div className="glass rounded-2xl overflow-hidden animate-pulse">
      <div className="h-40 bg-iv-surface/50" />
      <div className="p-5 space-y-3">
        <div className="h-5 w-32 rounded bg-iv-surface" />
        <div className="h-3.5 w-24 rounded bg-iv-surface" />
        <div className="h-2 w-full rounded bg-iv-surface" />
        <div className="h-4 w-20 rounded bg-iv-surface" />
      </div>
    </div>
  );
}

export function VehicleCard({
  vehicleId,
  displayName,
  manufacturer,
  model,
  modelYear,
  imageUrl,
  connectorStatus,
  status,
  loading,
  onDelete,
  onAfterRefresh,
}: VehicleCardProps) {
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (loading) return <CardSkeleton />;

  const battery = status?.latest_battery_level ?? null;
  const range = status?.latest_range_km;
  const odometer = status?.odometer_km;
  const title =
    displayName ||
    status?.display_name ||
    (status?.vin_last4 ? `Vehicle •••${status.vin_last4}` : "Vehicle");
  const modelName = model || status?.model || manufacturer || status?.manufacturer || "";
  const year = modelYear || status?.model_year;
  const manufacturerName = manufacturer || status?.manufacturer || "";
  const displayModelName = modelName.toLowerCase().includes(manufacturerName.toLowerCase()) ? modelName : `${manufacturerName} ${modelName}`;
  const imgSrc = imageUrl || status?.image_url;
  const locked = status?.doors_locked;
  const isLocked = locked && locked.toLowerCase().includes("locked");
  const isOnline = status?.is_online;
  const cStatus = connectorStatus || status?.connector_status;
  const chargingState = status?.latest_charging_state;
  const isCharging = chargingState && chargingState.toLowerCase().includes("charging");

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirmDelete) {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
      return;
    }
    setDeleting(true);
    try {
      await onDelete?.(vehicleId);
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  return (
    <div
      onClick={() => router.push(`/vehicles/${vehicleId}`)}
      className="glass rounded-2xl overflow-hidden cursor-pointer transition-all duration-300 hover:glow-green hover:border-iv-green/30 group relative flex flex-col"
    >
      {/* Car image */}
      <div className="relative h-44 w-full bg-gradient-to-b from-iv-surface/30 to-iv-surface/60 flex items-center justify-center overflow-hidden">
        {imgSrc ? (
          <img
            src={imgSrc}
            alt={title}
            className="h-full w-full object-contain p-4 drop-shadow-lg group-hover:scale-105 transition-transform duration-500"
          />
        ) : (
          <div className="flex flex-col items-center gap-2 text-iv-muted/30">
            <svg width="80" height="48" viewBox="0 0 80 48" fill="none" className="opacity-50">
              <path d="M16 36h-4a4 4 0 01-4-4v-8l8-12h36l12 12v8a4 4 0 01-4 4h-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <circle cx="22" cy="36" r="5" stroke="currentColor" strokeWidth="2" />
              <circle cx="58" cy="36" r="5" stroke="currentColor" strokeWidth="2" />
              <path d="M16 16l4-4h28l8 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </div>
        )}

        {/* Status indicators overlay */}
        <div className="absolute top-3 right-3 flex items-center gap-1.5">
          {isOnline !== null && isOnline !== undefined && (
            <span
              className="flex h-7 w-7 items-center justify-center rounded-full bg-black/40 backdrop-blur-sm"
              title={isOnline ? "Online" : "Offline"}
            >
              {isOnline ? (
                <Wifi size={13} className="text-iv-green" />
              ) : (
                <WifiOff size={13} className="text-iv-muted/60" />
              )}
            </span>
          )}
          {locked && (
            <span
              className="flex h-7 w-7 items-center justify-center rounded-full bg-black/40 backdrop-blur-sm"
              title={isLocked ? "Locked" : "Unlocked"}
            >
              {isLocked ? (
                <Lock size={13} className="text-iv-green" />
              ) : (
                <LockOpen size={13} className="text-iv-warning" />
              )}
            </span>
          )}
          {onDelete && (
            <button
              onClick={handleDelete}
              disabled={deleting}
              className={`flex h-7 w-7 items-center justify-center rounded-full backdrop-blur-sm transition-colors ${
                confirmDelete
                  ? "bg-iv-danger/60 text-white"
                  : "bg-black/40 text-iv-muted/60 hover:text-iv-danger hover:bg-iv-danger/30"
              } disabled:opacity-50`}
              title={confirmDelete ? "Click again to confirm" : "Remove vehicle"}
            >
              {deleting ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Trash2 size={13} />
              )}
            </button>
          )}
        </div>

        {/* Charging indicator */}
        {isCharging && (
          <div className="absolute top-3 left-3 flex items-center gap-1 rounded-full bg-iv-green/20 backdrop-blur-sm border border-iv-green/30 px-2 py-1">
            <Zap size={12} className="text-iv-green" />
            <span className="text-xs font-medium text-iv-green">Charging</span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-5 flex flex-col gap-3 flex-1">
        {/* Title row */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h3 className="truncate text-lg font-semibold text-iv-text group-hover:text-iv-green transition-colors">
                {title}
              </h3>
              <ConnectorDot status={cStatus} />
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-sm text-iv-muted">
                {displayModelName}
                {year ? ` ${year}` : ""}
              </span>
            </div>
          </div>
          <span className="flex items-center gap-1 text-xs text-iv-muted whitespace-nowrap flex-shrink-0 pt-1">
            <Clock size={11} />
            {formatTimeAgo(status?.last_updated ?? null)}
          </span>
        </div>

        {/* Data health badge */}
        <DataHealthBadge vehicleId={vehicleId} onRefreshTriggered={onAfterRefresh} />

        {/* Stats */}
        <div className="space-y-2.5 mt-auto">
          {battery !== null && <BatteryIndicator percentage={battery} />}

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <MapPin size={18} className="text-iv-cyan" />
              <span className="text-xs text-iv-muted">Range</span>
            </div>
            <span className="text-sm font-semibold text-iv-text">
              {range != null ? `${Math.round(range)}km` : "—"}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <Gauge size={18} className="text-iv-muted" />
              <span className="text-xs text-iv-muted">Odometer</span>
            </div>
            <span className="text-sm font-semibold text-iv-text">
              {odometer != null ? `${odometer.toLocaleString()}km` : "—"}
            </span>
          </div>
        </div>

        {/* View buttons */}
        <div className="mt-2 flex gap-2">
          <Link
            href={`/vehicles/${vehicleId}`}
            onClick={(e) => e.stopPropagation()}
            className="flex-1 flex items-center justify-center gap-1.5 rounded-xl bg-iv-green/10 border border-iv-green/20 px-4 py-2.5 text-sm font-medium text-iv-green transition-all hover:bg-iv-green hover:text-white hover:border-iv-green"
          >
            Overview
          </Link>
          <Link
            href={`/vehicles/${vehicleId}/statistics`}
            onClick={(e) => e.stopPropagation()}
            className="flex-1 flex items-center justify-center gap-1.5 rounded-xl bg-iv-cyan/10 border border-iv-cyan/20 px-4 py-2.5 text-sm font-medium text-iv-cyan transition-all hover:bg-iv-cyan hover:text-white hover:border-iv-cyan"
          >
            Statistics
            <ChevronRight size={14} />
          </Link>
        </div>
      </div>
    </div>
  );
}

export { CardSkeleton };
