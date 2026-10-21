"use client";

import { useState } from "react";
import {
  Car,
  CheckCircle2,
  Gauge,
  KeyRound,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Timer,
  Trash2,
  Wifi,
  XCircle,
} from "lucide-react";
import { PasswordInput } from "@/components/password-input";
import { skodaApi } from "@/lib/api/integrations";
import { vehiclesApi } from "@/lib/api/vehicles";

export type VehicleCardData = {
  id: string;
  display_name?: string | null;
  manufacturer?: string | null;
  model?: string | null;
  created_at?: string;
  last_fetch_at?: string | null;
  collection_enabled?: boolean;
  incognito_mode?: boolean;
  active_interval_seconds: number;
  parked_interval_seconds: number;
  wltp_range_km?: number | null;
  country_code?: string | null;
  connector_status?: string | null;
  needs_user_reauth_reason?: string | null;
  telemetry_source?: string | null;
  consecutive_failures?: number | null;
};

type Props = {
  v: VehicleCardData;
  onSaved: () => void;
  onToast: (status: "success" | "error", message: string) => void;
  onDelete?: () => void;
  onOpenCalibrate?: () => void;
  calibrateOpen?: boolean;
  children?: React.ReactNode;
  /** Hide chrome (header/tabs/delete) — embed connection form only. */
  embed?: boolean;
};

function intervalLabel(s: number) {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

function StatusPill({ v }: { v: VehicleCardData }) {
  const status = !v.collection_enabled
    ? "paused"
    : v.connector_status === "active" && (v.consecutive_failures ?? 0) >= 3
      ? "degraded"
      : v.connector_status || "unknown";
  const map: Record<string, { label: string; cls: string; icon: typeof Wifi }> = {
    active: { label: "Live", cls: "bg-iv-green/15 text-iv-green border-iv-green/25", icon: CheckCircle2 },
    paused: { label: "Paused", cls: "bg-iv-muted/10 text-iv-muted border-iv-border", icon: Wifi },
    degraded: { label: "Degraded", cls: "bg-iv-warning/15 text-iv-warning border-iv-warning/30", icon: XCircle },
    auth_failed: { label: "Login required", cls: "bg-iv-danger/15 text-iv-danger border-iv-danger/30", icon: ShieldCheck },
    token_error: { label: "Login required", cls: "bg-iv-danger/15 text-iv-danger border-iv-danger/30", icon: ShieldCheck },
  };
  const s = map[status] ?? {
    label: status,
    cls: "bg-iv-muted/10 text-iv-muted border-iv-border",
    icon: Wifi,
  };
  const Icon = s.icon;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${s.cls}`}>
      <Icon size={11} />
      {s.label}
    </span>
  );
}

export function VehicleSettingsCard({
  v,
  onSaved,
  onToast,
  onDelete,
  onOpenCalibrate,
  calibrateOpen,
  children,
  embed = false,
}: Props) {
  const [tab, setTab] = useState<"sync" | "connection">("connection");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [spin, setSpin] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [source, setSource] = useState(v.telemetry_source || "auto");
  const [syncOpen, setSyncOpen] = useState(false);

  const name = v.display_name || `${v.manufacturer || ""} ${v.model || ""}`.trim() || "Vehicle";

  const saveConnection = async () => {
    setBusy(true);
    try {
      if (email.trim() && password) {
        await vehiclesApi.reauthenticateVehicle(v.id, {
          skoda_username: email.trim(),
          skoda_password: password,
          skoda_spin: spin.trim() || undefined,
        });
      }
      if (apiKey.trim()) {
        await skodaApi.setVehicleApiKey(v.id, apiKey.trim());
      }
      if (source !== (v.telemetry_source || "auto")) {
        await skodaApi.setVehicleSource(v.id, source);
      }
      setEmail("");
      setPassword("");
      setSpin("");
      setApiKey("");
      onToast("success", `Connection saved for ${name}`);
      onSaved();
    } catch (e) {
      onToast("error", e instanceof Error ? e.message : "Could not save connection");
    } finally {
      setBusy(false);
    }
  };

  const mintKey = async () => {
    setBusy(true);
    try {
      await skodaApi.mintVehicleKey(v.id);
      onToast("success", "Official API key created for this car");
      onSaved();
    } catch (e) {
      onToast("error", e instanceof Error ? e.message : "Could not create API key");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={
        embed
          ? "rounded-xl border border-iv-border/60 bg-iv-bg/30 overflow-hidden"
          : "rounded-2xl border border-iv-border/80 bg-gradient-to-b from-iv-surface/80 to-iv-surface/40 overflow-hidden"
      }
    >
      {!embed && (
      <>
      {/* Header */}
      <div className="flex items-start gap-3 p-4 pb-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-iv-green/12 border border-iv-green/20">
          <Car size={18} className="text-iv-green" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-iv-text truncate">{name}</h3>
            <StatusPill v={v} />
          </div>
          <p className="text-[11px] text-iv-muted mt-0.5">
            {v.last_fetch_at
              ? `Last sync ${new Date(v.last_fetch_at).toLocaleString()}`
              : `Added ${v.created_at ? new Date(v.created_at).toLocaleDateString() : "—"}`}
            {" · "}
            Active {intervalLabel(v.active_interval_seconds)} · Parked {intervalLabel(v.parked_interval_seconds)}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onOpenCalibrate}
            className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
              calibrateOpen
                ? "bg-iv-cyan/15 text-iv-cyan border border-iv-cyan/30"
                : "border border-iv-border text-iv-muted hover:text-iv-cyan hover:border-iv-cyan/40"
            }`}
          >
            <Gauge size={13} className="inline mr-1" />
            Calibrate
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="rounded-lg px-2.5 py-1.5 text-xs font-medium border border-iv-border text-iv-muted hover:text-iv-danger hover:border-iv-danger/40 transition-colors"
          >
            <Trash2 size={13} className="inline mr-1" />
            Remove
          </button>
        </div>
      </div>

      {v.needs_user_reauth_reason && (
        <div className="mx-4 mb-3 rounded-xl border border-iv-danger/30 bg-iv-danger/10 px-3 py-2 text-xs text-iv-danger">
          {v.needs_user_reauth_reason}
        </div>
      )}

      {/* Tabs */}
      <div className="px-4 flex gap-1 border-b border-iv-border/60">
        {(
          [
            ["connection", "Connection", KeyRound],
            ["sync", "Sync & data", Timer],
          ] as const
        ).map(([id, label, Icon]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors ${
              tab === id
                ? "border-iv-green text-iv-green"
                : "border-transparent text-iv-muted hover:text-iv-text"
            }`}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>
      </>
      )}

      <div className={embed ? "p-3 space-y-3" : "p-4 space-y-4"}>
        {(embed || tab === "connection") && (
          <>
            {embed && (
              <div className="flex items-center gap-2 mb-1">
                <KeyRound size={13} className="text-iv-cyan" />
                <p className="text-xs font-medium text-iv-text">Škoda connection</p>
              </div>
            )}
            <div>
              <p className="text-[11px] font-medium text-iv-muted uppercase tracking-wide mb-2">
                Data source
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(
                  [
                    ["auto", "Auto"],
                    ["login", "MyŠkoda Login"],
                    ["public", "MyŠkoda Public API"],
                  ] as const
                ).map(([opt, label]) => (
                  <button
                    key={opt}
                    type="button"
                    disabled={busy}
                    onClick={() => setSource(opt)}
                    className={`rounded-xl px-3 py-2 text-xs font-medium transition-all ${
                      source === opt
                        ? "bg-iv-green/15 text-iv-green border border-iv-green/30 shadow-sm"
                        : "border border-iv-border text-iv-muted hover:text-iv-text hover:border-iv-border/80"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-iv-muted mt-2 leading-relaxed">
                <strong className="text-iv-text">Auto</strong> uses Login when saved, otherwise the official API key.{" "}
                <strong className="text-iv-text">Login</strong> enables wake, lock, climate.{" "}
                <strong className="text-iv-text">Public API</strong> is official read/commands only.
              </p>
            </div>

            <div className="rounded-xl border border-iv-border/60 bg-iv-bg/40 p-3 space-y-2">
              <p className="text-[11px] font-medium text-iv-muted uppercase tracking-wide">
                MyŠkoda login <span className="normal-case text-iv-muted/70">— optional</span>
              </p>
              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  type="email"
                  autoComplete="username"
                  placeholder="MyŠkoda email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={busy}
                  className="flex-1 rounded-lg border border-iv-border bg-iv-surface px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted"
                />
                <PasswordInput
                  autoComplete="new-password"
                  placeholder="Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={busy}
                  wrapperClassName="flex-1"
                  className="w-full rounded-lg border border-iv-border bg-iv-surface px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted"
                />
                <PasswordInput
                  autoComplete="off"
                  placeholder="S-PIN"
                  value={spin}
                  onChange={(e) => setSpin(e.target.value)}
                  disabled={busy}
                  wrapperClassName="w-full sm:w-28"
                  className="w-full rounded-lg border border-iv-border bg-iv-surface px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted"
                />
              </div>
            </div>

            <div className="rounded-xl border border-iv-border/60 bg-iv-bg/40 p-3 space-y-2">
              <p className="text-[11px] font-medium text-iv-muted uppercase tracking-wide">
                Official API key <span className="normal-case text-iv-muted/70">— for this car</span>
              </p>
              <div className="flex flex-col sm:flex-row gap-2">
                <PasswordInput
                  autoComplete="off"
                  placeholder="msk_… paste or create from login"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  disabled={busy}
                  wrapperClassName="flex-1"
                  className="w-full rounded-lg border border-iv-border bg-iv-surface px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted"
                />
                <button
                  type="button"
                  disabled={busy || !email.trim() || !password}
                  onClick={mintKey}
                  className="rounded-lg border border-iv-green/30 bg-iv-green/10 px-3 py-2 text-xs font-medium text-iv-green hover:bg-iv-green/15 disabled:opacity-40 whitespace-nowrap"
                >
                  Create from login
                </button>
              </div>
              <p className="text-[11px] text-iv-muted">
                Keys are VIN-bound and expire — “Create from login” needs the email/password above.
              </p>
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                disabled={busy || (!email.trim() && !password && !apiKey.trim() && source === (v.telemetry_source || "auto"))}
                onClick={saveConnection}
                className="rounded-xl bg-iv-green px-4 py-2 text-xs font-semibold text-iv-bg hover:opacity-90 disabled:opacity-40"
              >
                {busy ? <Loader2 size={13} className="animate-spin inline mr-1" /> : <RefreshCw size={13} className="inline mr-1" />}
                Save connection
              </button>
            </div>
          </>
        )}

        {!embed && tab === "sync" && (
          <div className="space-y-3">
            <p className="text-xs text-iv-muted">
              Collection, privacy, intervals, and region for this vehicle.
            </p>
            {children}
            <button
              type="button"
              onClick={() => setSyncOpen((o) => !o)}
              className="text-xs text-iv-cyan hover:underline"
            >
              {syncOpen ? "Hide advanced interval summary" : "Show what these intervals mean"}
            </button>
            {syncOpen && (
              <div className="rounded-lg bg-iv-bg/50 border border-iv-border/50 p-3 text-[11px] text-iv-muted leading-relaxed">
                <p>
                  <strong className="text-iv-text">Active</strong> = car is driving, charging, or climate is on — poll every{" "}
                  {intervalLabel(v.active_interval_seconds)}.
                </p>
                <p className="mt-1">
                  <strong className="text-iv-text">Parked</strong> = deep sleep — light check every{" "}
                  {intervalLabel(v.parked_interval_seconds)}. When the car becomes active, polling speeds up automatically.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
