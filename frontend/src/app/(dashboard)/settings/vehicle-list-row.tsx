"use client";

import { useState } from "react";
import {
  Car,
  ChevronDown,
  Gauge,
  KeyRound,
  Loader2,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { PasswordInput } from "@/components/password-input";
import { skodaApi } from "@/lib/api/integrations";
import { vehiclesApi } from "@/lib/api/vehicles";

export type VehicleRow = {
  id: string;
  display_name?: string | null;
  manufacturer?: string | null;
  model?: string | null;
  created_at?: string;
  last_fetch_at?: string | null;
  collection_enabled?: boolean;
  connector_status?: string | null;
  needs_user_reauth_reason?: string | null;
  last_error_text?: string | null;
  telemetry_source?: string | null;
  consecutive_failures?: number | null;
  has_skoda_login?: boolean;
  has_api_key?: boolean;
  api_key_expires_at?: string | null;
  api_key_expired?: boolean;
  api_key_expires_in_days?: number | null;
};

function intervalLabel(s: number) {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

function statusDot(v: VehicleRow) {
  if (!v.collection_enabled) return { label: "Paused", color: "bg-iv-muted" };
  if (v.connector_status === "auth_failed" || v.connector_status === "token_error")
    return { label: "Login required", color: "bg-iv-danger" };
  if (v.connector_status === "active" && (v.consecutive_failures ?? 0) >= 3)
    return { label: "Degraded", color: "bg-iv-warning" };
  if (v.connector_status === "active") return { label: "Live", color: "bg-iv-green" };
  return { label: v.connector_status || "Idle", color: "bg-iv-muted" };
}

type Props = {
  v: VehicleRow;
  expanded: boolean;
  onToggle: () => void;
  onSaved: () => void;
  onToast: (status: "success" | "error", message: string) => void;
  onDelete: () => void;
  onOpenCalibrate: () => void;
  /** Sync form (intervals, toggles, WLTP…) rendered inside the expanded panel. */
  syncForm?: React.ReactNode;
  alert?: React.ReactNode;
  calibrate?: React.ReactNode;
};

/**
 * Compact vehicle row → one flat expand panel.
 * No nested cards: collapsed = single line summary; open = form only.
 */
export function VehicleListRow({
  v,
  expanded,
  onToggle,
  onSaved,
  onToast,
  onDelete,
  onOpenCalibrate,
  syncForm,
  alert,
  calibrate,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [spin, setSpin] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [source, setSource] = useState(v.telemetry_source || "auto");

  const name = v.display_name || `${v.manufacturer || ""} ${v.model || ""}`.trim() || "Vehicle";
  const st = statusDot(v);

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
      if (apiKey.trim()) await skodaApi.setVehicleApiKey(v.id, apiKey.trim());
      if (source !== (v.telemetry_source || "auto")) await skodaApi.setVehicleSource(v.id, source);
      setEmail("");
      setPassword("");
      setSpin("");
      setApiKey("");
      onToast("success", "Saved");
      onSaved();
    } catch (e) {
      onToast("error", e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const mintKey = async () => {
    setBusy(true);
    try {
      // Save new credentials first so mint uses the latest login
      if (email.trim() && password) {
        await vehiclesApi.reauthenticateVehicle(v.id, {
          skoda_username: email.trim(),
          skoda_password: password,
          skoda_spin: spin.trim() || undefined,
        });
      }
      await skodaApi.mintVehicleKey(v.id);
      setEmail("");
      setPassword("");
      setSpin("");
      onToast("success", "API key created");
      onSaved();
    } catch (e) {
      onToast("error", e instanceof Error ? e.message : "Could not create key");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border-b border-iv-border/60 last:border-b-0">
      {/* Collapsed row — one line */}
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-iv-surface/50 transition-colors"
      >
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-iv-green/10">
          <Car size={15} className="text-iv-green" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-iv-text truncate">{name}</span>
            <span className="inline-flex items-center gap-1 text-[11px] text-iv-muted">
              <span className={`h-1.5 w-1.5 rounded-full ${st.color}`} />
              {st.label}
            </span>
            {/* Connection badges — what’s saved */}
            {v.has_skoda_login ? (
              <span className="rounded-full bg-iv-cyan/10 border border-iv-cyan/25 px-2 py-0.5 text-[10px] text-iv-cyan">
                Login saved
              </span>
            ) : (
              <span className="rounded-full bg-iv-muted/10 border border-iv-border px-2 py-0.5 text-[10px] text-iv-muted">
                No login
              </span>
            )}
            {v.has_api_key ? (
              v.api_key_expired ? (
                <span className="rounded-full bg-iv-danger/10 border border-iv-danger/30 px-2 py-0.5 text-[10px] text-iv-danger">
                  API key expired
                </span>
              ) : (
                <span className="rounded-full bg-iv-green/10 border border-iv-green/25 px-2 py-0.5 text-[10px] text-iv-green">
                  API key
                  {v.api_key_expires_in_days != null
                    ? ` · ${v.api_key_expires_in_days}d`
                    : ""}
                </span>
              )
            ) : (
              <span className="rounded-full bg-iv-muted/10 border border-iv-border px-2 py-0.5 text-[10px] text-iv-muted">
                No API key
              </span>
            )}
          </div>
          <p className="text-[11px] text-iv-muted truncate">
            {v.created_at ? `Added ${new Date(v.created_at).toLocaleDateString()}` : ""}
            {v.last_fetch_at
              ? `  ·  Last fetch ${new Date(v.last_fetch_at).toLocaleString()}`
              : "  ·  No sync yet"}
          </p>
          {(v.needs_user_reauth_reason || v.api_key_expired || v.last_error_text) && (
            <p className="text-[11px] text-iv-danger truncate mt-0.5">
              {v.needs_user_reauth_reason ||
                (v.api_key_expired
                  ? "API key expired — create a new one below."
                  : v.last_error_text)}
            </p>
          )}
        </div>
        <ChevronDown
          size={16}
          className={`shrink-0 text-iv-muted transition-transform ${expanded ? "rotate-180" : ""}`}
        />
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-iv-border/40 bg-iv-bg/20">
          {alert}

          {v.needs_user_reauth_reason && (
            <p className="text-xs text-iv-danger pt-3">{v.needs_user_reauth_reason}</p>
          )}

          {/* Connection — flat form, no inner card chrome */}
          <div className="pt-3 space-y-3">
            <div className="flex items-center gap-2">
              <KeyRound size={13} className="text-iv-cyan" />
              <h4 className="text-xs font-semibold text-iv-text uppercase tracking-wide">Connection</h4>
              {v.has_skoda_login && (
                <span className="text-[10px] text-iv-green">✓ login saved</span>
              )}
              {v.has_api_key && !v.api_key_expired && (
                <span className="text-[10px] text-iv-green">
                  ✓ API key{v.api_key_expires_in_days != null ? ` (${v.api_key_expires_in_days}d)` : ""}
                </span>
              )}
              {v.api_key_expired && (
                <span className="text-[10px] text-iv-danger">✗ API key expired</span>
              )}
            </div>

            <div className="flex flex-wrap gap-1.5">
              {(
                [
                  ["auto", "Auto"],
                  ["login", "MyŠkoda Login"],
                  ["public", "Public API"],
                ] as const
              ).map(([opt, label]) => (
                <button
                  key={opt}
                  type="button"
                  disabled={busy}
                  onClick={() => setSource(opt)}
                  className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                    source === opt
                      ? "bg-iv-green/15 text-iv-green border border-iv-green/30"
                      : "border border-iv-border text-iv-muted hover:text-iv-text"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <input
                type="email"
                autoComplete="username"
                placeholder="MyŠkoda email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={busy}
                className="rounded-lg border border-iv-border bg-iv-surface px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted"
              />
              <PasswordInput
                autoComplete="new-password"
                placeholder={v.has_skoda_login ? "Password saved — enter to replace" : "Password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={busy}
                wrapperClassName="w-full"
                className="w-full rounded-lg border border-iv-border bg-iv-surface px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted"
              />
              <PasswordInput
                autoComplete="off"
                placeholder="S-PIN (optional)"
                value={spin}
                onChange={(e) => setSpin(e.target.value)}
                disabled={busy}
                wrapperClassName="w-full"
                className="w-full rounded-lg border border-iv-border bg-iv-surface px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted"
              />
            </div>

            <div className="flex flex-col sm:flex-row gap-2">
              <PasswordInput
                autoComplete="off"
                placeholder={
                  v.has_api_key && !v.api_key_expired
                    ? "API key saved — enter to replace"
                    : v.api_key_expired
                      ? "API key expired — paste or create new"
                      : "API key msk_… (paste or create)"
                }
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                disabled={busy}
                wrapperClassName="flex-1"
                className="w-full rounded-lg border border-iv-border bg-iv-surface px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted"
              />
              <button
                type="button"
                disabled={busy || (!v.has_skoda_login && (!email.trim() || !password))}
                onClick={mintKey}
                className="rounded-lg border border-iv-border px-3 py-2 text-xs text-iv-muted hover:text-iv-green hover:border-iv-green/40 disabled:opacity-40 whitespace-nowrap"
              >
                Create key from login
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={saveConnection}
                className="rounded-lg bg-iv-green px-3 py-1.5 text-xs font-semibold text-iv-bg hover:opacity-90 disabled:opacity-40"
              >
                {busy ? (
                  <Loader2 size={12} className="animate-spin inline mr-1" />
                ) : (
                  <RefreshCw size={12} className="inline mr-1" />
                )}
                Save
              </button>
              <button
                type="button"
                onClick={onOpenCalibrate}
                className="rounded-lg border border-iv-border px-3 py-1.5 text-xs text-iv-muted hover:text-iv-cyan"
              >
                <Gauge size={12} className="inline mr-1" />
                Calibrate
              </button>
              <button
                type="button"
                onClick={onDelete}
                className="rounded-lg border border-iv-border px-3 py-1.5 text-xs text-iv-muted hover:text-iv-danger hover:border-iv-danger/40"
              >
                <Trash2 size={12} className="inline mr-1" />
                Remove
              </button>
            </div>
          </div>

          {/* Sync / intervals / calibrate — caller-owned form, not a nested card */}
          {(syncForm || calibrate) && (
            <div className="space-y-3 border-t border-iv-border/40 pt-3">
              <h4 className="text-xs font-semibold text-iv-text uppercase tracking-wide">
                Sync & data
              </h4>
              {syncForm}
              {calibrate}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
