"use client";
/**
 * DataHealthBadge — per-vehicle telemetry-freshness status indicator.
 * Calls GET /api/v1/vehicles/{id}/data-health and renders a compact
 * status pill + (optional) "Refresh" button.
 *
 * Status semantics (from backend):
 *   live   — most recent telemetry within the last hour
 *   stale  — last telemetry 1-24h ago
 *   down   — no telemetry in >24h
 *   unknown — never received any telemetry for this vehicle
 */
import { useEffect, useState } from "react";
import { Activity, AlertCircle, CheckCircle2, Clock, Loader2, RefreshCw } from "lucide-react";

import { vehiclesApi } from "@/lib/api/vehicles";

export interface DataHealthTimelineEntry {
  last_at: string | null;
  age_minutes: number | null;
}

export interface VehicleDataHealth {
  vehicle_id: string;
  vin_last4: string;
  display_name: string | null;
  status: "live" | "stale" | "down" | "unknown";
  last_telemetry_at: string | null;
  minutes_since_last_telemetry: number | null;
  timeline: Record<string, DataHealthTimelineEntry>;
  has_ongoing_trip: boolean;
  is_currently_charging: boolean;
  collection_enabled: boolean | null;
  last_fetch_at: string | null;
  refresh_recommended: boolean;
  refresh_reason: string | null;
  generated_at: string;
}

interface DataHealthBadgeProps {
  vehicleId: string;
  /** Optional pre-fetched health (skips the initial fetch if provided) */
  initial?: VehicleDataHealth | null;
  /** Called after a successful manual refresh triggers — parent may re-fetch status */
  onRefreshTriggered?: () => void;
}

const STATUS_STYLES: Record<
  VehicleDataHealth["status"],
  { dot: string; pill: string; text: string; icon: typeof CheckCircle2 }
> = {
  live: {
    dot: "bg-iv-green",
    pill: "bg-iv-green/10 border-iv-green/30 text-iv-green",
    text: "Live",
    icon: CheckCircle2,
  },
  stale: {
    dot: "bg-iv-warning",
    pill: "bg-iv-warning/10 border-iv-warning/30 text-iv-warning",
    text: "Stale",
    icon: Clock,
  },
  down: {
    dot: "bg-iv-danger",
    pill: "bg-iv-danger/10 border-iv-danger/30 text-iv-danger",
    text: "Down",
    icon: AlertCircle,
  },
  unknown: {
    dot: "bg-iv-muted",
    pill: "bg-iv-muted/10 border-iv-muted/30 text-iv-muted",
    text: "Unknown",
    icon: Activity,
  },
};

function formatAge(minutes: number | null | undefined): string {
  if (minutes == null) return "no data";
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return `${Math.floor(days / 7)}w ago`;
}

export function DataHealthBadge({
  vehicleId,
  initial,
  onRefreshTriggered,
}: DataHealthBadgeProps) {
  const [state, setState] = useState<{
    health: VehicleDataHealth | null;
    loading: boolean;
    error: string | null;
  }>(() => ({
    health: initial ?? null,
    loading: !initial,
    error: null,
  }));
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await vehiclesApi.getVehicleDataHealth(vehicleId);
        if (cancelled) return;
        setState({ health: data, loading: false, error: null });
      } catch (e: any) {
        if (cancelled) return;
        setState((s) => ({ ...s, loading: false, error: e?.message ?? "Failed to load data health" }));
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [vehicleId]);

  const handleRefresh = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (refreshing) return;
    setRefreshing(true);
    try {
      await vehiclesApi.refreshVehicle(vehicleId);
      onRefreshTriggered?.();
      setState((s) =>
        s.health ? { ...s, health: { ...s.health, status: "live", refresh_recommended: false } } : s,
      );
    } catch (e: any) {
      setState((s) => ({ ...s, error: e?.message ?? "Refresh failed" }));
    } finally {
      setRefreshing(false);
    }
  };

  const { health, loading, error } = state;

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-iv-surface/40 px-2.5 py-1.5 border border-iv-muted/20">
        <Loader2 size={12} className="animate-spin text-iv-muted" />
        <span className="text-xs text-iv-muted">checking data…</span>
      </div>
    );
  }

  if (error || !health) {
    return (
      <div
        className="flex items-center gap-2 rounded-lg bg-iv-surface/40 px-2.5 py-1.5 border border-iv-muted/20"
        title={error ?? "Data health unavailable"}
      >
        <span className="h-2 w-2 rounded-full bg-iv-muted" />
        <span className="text-xs text-iv-muted">Data health unavailable</span>
      </div>
    );
  }

  const style = STATUS_STYLES[health.status];
  const Icon = style.icon;
  const ageLabel = formatAge(health.minutes_since_last_telemetry);

  return (
    <div
      className={`flex items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 ${style.pill}`}
      title={health.refresh_recommended && health.refresh_reason ? health.refresh_reason : undefined}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className={`h-2 w-2 flex-shrink-0 rounded-full ${style.dot}`} />
        <Icon size={12} className="flex-shrink-0" />
        <span className="text-xs font-medium whitespace-nowrap">
          {style.text} <span className="opacity-70">· {ageLabel}</span>
        </span>
      </div>
      {health.refresh_recommended && (
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="flex items-center gap-1 rounded-md bg-black/20 hover:bg-black/30 px-1.5 py-0.5 text-[10px] font-medium transition-colors disabled:opacity-50"
          aria-label="Refresh vehicle data"
        >
          <RefreshCw size={10} className={refreshing ? "animate-spin" : ""} />
          {refreshing ? "…" : "Refresh"}
        </button>
      )}
    </div>
  );
}
