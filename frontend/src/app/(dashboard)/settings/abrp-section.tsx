"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  ExternalLink,
  Loader2,
  PlugZap,
  RefreshCw,
  Trash2,
  XCircle,
} from "lucide-react";
import {
  integrationsApi,
  type AbrpConnection,
  type AbrpConnectionUpdate,
  type AbrpSettings,
} from "@/lib/api/integrations";
import { PasswordInput } from "@/components/password-input";

function MiniToast({
  status,
  message,
  onDismiss,
}: {
  status: "success" | "error";
  message: string;
  onDismiss: () => void;
}) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 4000);
    return () => clearTimeout(t);
  }, [onDismiss]);
  return (
    <div
      className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs ${
        status === "success"
          ? "bg-iv-green/10 text-iv-green"
          : "bg-iv-danger/10 text-iv-danger"
      }`}
    >
      {status === "success" ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
      <span className="flex-1">{message}</span>
      <button type="button" onClick={onDismiss} className="opacity-60 hover:opacity-100">
        ×
      </button>
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <label aria-label={label} className="relative inline-flex items-center cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="sr-only peer"
      />
      <div className="w-11 h-6 bg-iv-border peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-iv-green transition-colors"></div>
    </label>
  );
}

const inputClasses =
  "w-full rounded-lg bg-iv-surface border border-iv-border px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted/60 focus:outline-none focus:border-iv-green/50 transition-colors";

const btnPrimaryClasses =
  "rounded-lg bg-iv-green/15 px-3 py-2 text-xs font-medium text-iv-green transition-colors hover:bg-iv-green/25 disabled:opacity-50 disabled:cursor-not-allowed";

function formatRelative(iso: string | null): string {
  if (!iso) return "never";
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return "never";
  const diff = Math.max(0, Date.now() - ts) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function AbrpSection() {
  const [settings, setSettings] = useState<AbrpSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ status: "success" | "error"; message: string } | null>(null);
  const [apiKeyDraft, setApiKeyDraft] = useState("");
  const [tokenDrafts, setTokenDrafts] = useState<Record<string, string>>({});
  const [typecodeDrafts, setTypecodeDrafts] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmClearId, setConfirmClearId] = useState<string | null>(null);
  const [confirmClearApiKey, setConfirmClearApiKey] = useState(false);

  const applySettings = useCallback((s: AbrpSettings) => {
    setSettings(s);
    const t: Record<string, string> = {};
    const c: Record<string, string> = {};
    for (const r of s.connections) {
      t[r.vehicle_id] = "";
      c[r.vehicle_id] = r.car_model_typecode ?? "";
    }
    setTokenDrafts(t);
    setTypecodeDrafts(c);
  }, []);

  const load = useCallback(async () => {
    try {
      applySettings(await integrationsApi.getAbrp());
    } catch {
      setToast({ status: "error", message: "Failed to load ABRP settings" });
    } finally {
      setLoading(false);
    }
  }, [applySettings]);

  useEffect(() => {
    load();
  }, [load]);

  const saveApiKey = async (apiKey: string) => {
    setBusyId("__apikey__");
    try {
      const s = await integrationsApi.updateAbrpSettings({ api_key: apiKey });
      applySettings(s);
      setApiKeyDraft("");
      setConfirmClearApiKey(false);
      setToast({
        status: "success",
        message: apiKey === "" ? "ABRP API key cleared" : "ABRP API key saved",
      });
    } catch (e) {
      setToast({
        status: "error",
        message: e instanceof Error ? e.message : "Failed to save API key",
      });
    } finally {
      setBusyId(null);
    }
  };

  const saveVehicle = async (vehicleId: string, body: AbrpConnectionUpdate) => {
    setBusyId(vehicleId);
    try {
      const s = await integrationsApi.upsertAbrpVehicle(vehicleId, body);
      applySettings(s);
      setToast({ status: "success", message: "ABRP vehicle settings saved" });
      if (body.token) {
        setTokenDrafts((p) => ({ ...p, [vehicleId]: "" }));
      }
    } catch (e) {
      setToast({
        status: "error",
        message: e instanceof Error ? e.message : "Save failed",
      });
    } finally {
      setBusyId(null);
    }
  };

  const clearToken = async (vehicleId: string) => {
    setBusyId(vehicleId);
    try {
      const s = await integrationsApi.clearAbrpToken(vehicleId);
      applySettings(s);
      setTokenDrafts((p) => ({ ...p, [vehicleId]: "" }));
      setToast({ status: "success", message: "ABRP car token cleared" });
    } catch {
      setToast({ status: "error", message: "Failed to clear token" });
    } finally {
      setBusyId(null);
      setConfirmClearId(null);
    }
  };

  const refreshNextCharge = async (vehicleId: string) => {
    setBusyId(vehicleId);
    try {
      const res = await integrationsApi.refreshNextCharge(vehicleId);
      setSettings((prev) =>
        prev
          ? {
              ...prev,
              connections: prev.connections.map((r) =>
                r.vehicle_id === vehicleId
                  ? {
                      ...r,
                      next_charge_pct: res.next_charge_pct,
                      next_charge_fetched_at: res.fetched_at,
                      last_error_text: res.error ?? r.last_error_text,
                    }
                  : r,
              ),
            }
          : prev,
      );
      if (res.error) {
        setToast({ status: "error", message: res.error });
      } else {
        setToast({
          status: "success",
          message:
            res.next_charge_pct != null
              ? `ABRP plan: charge to ${res.next_charge_pct}%`
              : "No charge goal in current ABRP plan",
        });
      }
    } catch {
      setToast({ status: "error", message: "Failed to fetch next charge" });
    } finally {
      setBusyId(null);
    }
  };

  const rows: AbrpConnection[] = settings?.connections ?? [];
  const hasApiKey = settings?.has_api_key ?? false;

  return (
    <div className="space-y-5">
      {toast && (
        <MiniToast status={toast.status} message={toast.message} onDismiss={() => setToast(null)} />
      )}

      <div className="flex items-start gap-2 text-xs text-iv-muted leading-relaxed">
        <PlugZap size={14} className="mt-0.5 flex-shrink-0 text-iv-green" />
        <p>
          Push live SOC, charging and position data to{" "}
          <a
            href="https://abetterrouteplanner.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-iv-green hover:underline inline-flex items-center gap-0.5"
          >
            A Better Route Planner
            <ExternalLink size={11} />
          </a>{" "}
          so your trips use accurate live data. You need two free credentials from your ABRP
          account: an <strong className="text-iv-text">API key</strong> and a{" "}
          <strong className="text-iv-text">car token</strong> per vehicle. Disabled by default.
          Remote vehicle control from ABRP is not supported (ABRP-side limitation).
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 size={20} className="animate-spin text-iv-muted" />
        </div>
      ) : (
        <>
          {/* ── User-level: API key ─────────────────────────────────────── */}
          <div className="rounded-lg border border-iv-border bg-iv-surface/40 p-4 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-iv-text">Your ABRP API key</p>
                <p className="text-xs text-iv-muted mt-0.5 leading-relaxed">
                  Free Telemetry API key from your ABRP account →{" "}
                  <a
                    href="https://abetterrouteplanner.com/resources/api"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-iv-green hover:underline inline-flex items-center gap-0.5"
                  >
                    Manage telemetry API keys
                    <ExternalLink size={11} />
                  </a>
                  . Used for every vehicle below.
                </p>
              </div>
              {hasApiKey && (
                <span className="inline-flex items-center rounded-full bg-iv-green/10 border border-iv-green/20 px-2.5 py-1 text-xs text-iv-green">
                  saved: {settings?.api_key_hint}
                </span>
              )}
            </div>

            <div className="flex flex-col sm:flex-row gap-2">
              <PasswordInput
                className={inputClasses}
                placeholder={hasApiKey ? "••••••  (enter to replace)" : "Paste ABRP API key"}
                value={apiKeyDraft}
                onChange={(e) => setApiKeyDraft(e.target.value)}
                autoComplete="off"
                wrapperClassName="flex-1"
              />
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className={btnPrimaryClasses}
                  disabled={busyId === "__apikey__" || !apiKeyDraft}
                  onClick={() => saveApiKey(apiKeyDraft)}
                >
                  {busyId === "__apikey__" ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    "Save API key"
                  )}
                </button>
                {hasApiKey &&
                  (confirmClearApiKey ? (
                    <span className="flex items-center gap-2 text-xs">
                      <span className="text-iv-muted">Clear?</span>
                      <button
                        type="button"
                        className="text-iv-danger hover:underline"
                        onClick={() => saveApiKey("")}
                      >
                        Yes
                      </button>
                      <button
                        type="button"
                        className="text-iv-muted hover:underline"
                        onClick={() => setConfirmClearApiKey(false)}
                      >
                        No
                      </button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 text-xs text-iv-muted hover:text-iv-danger transition-colors"
                      onClick={() => setConfirmClearApiKey(true)}
                    >
                      <Trash2 size={12} /> Clear
                    </button>
                  ))}
              </div>
            </div>

            {!hasApiKey && (
              <p className="text-xs text-iv-warning">
                Add your API key before enabling any vehicle.
              </p>
            )}
          </div>

          {/* ── Per-vehicle: car token ──────────────────────────────────── */}
          <div>
            <p className="text-xs font-medium text-iv-muted uppercase tracking-wide mb-2">
              Vehicle tokens
            </p>
            {rows.length === 0 ? (
              <p className="text-sm text-iv-muted text-center py-6">No vehicles linked yet</p>
            ) : (
              <div className="space-y-3">
                {rows.map((row) => {
                  const tokenDraft = tokenDrafts[row.vehicle_id] ?? "";
                  const typecodeDraft = typecodeDrafts[row.vehicle_id] ?? "";
                  const busy = busyId === row.vehicle_id;
                  return (
                    <div
                      key={row.vehicle_id}
                      className="rounded-lg border border-iv-border bg-iv-surface/40 p-4 space-y-3"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-iv-text">
                            {row.display_name || "Vehicle"}
                          </p>
                          <p className="text-xs text-iv-muted mt-0.5">
                            Last sent: {formatRelative(row.last_sent_at)}
                            {row.consecutive_failures > 0 && (
                              <span className="text-iv-danger">
                                {" "}
                                · {row.consecutive_failures} failure
                                {row.consecutive_failures > 1 ? "s" : ""}
                              </span>
                            )}
                          </p>
                        </div>
                        <Toggle
                          checked={row.enabled}
                          disabled={busy || !hasApiKey}
                          label={`ABRP sync for ${row.display_name || "vehicle"}`}
                          onChange={(v) =>
                            saveVehicle(row.vehicle_id, {
                              enabled: v,
                              car_model_typecode: typecodeDraft || undefined,
                            })
                          }
                        />
                      </div>

                      {row.last_error_text && (
                        <p className="text-xs text-iv-danger">{row.last_error_text}</p>
                      )}

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <div>
                          <label className="block text-xs text-iv-muted mb-1">
                            ABRP car token{" "}
                            {row.has_token && row.token_hint ? `(saved: ${row.token_hint})` : ""}
                          </label>
                          <PasswordInput
                            className={inputClasses}
                            placeholder={
                              row.has_token ? "••••••  (enter to replace)" : "Paste car token"
                            }
                            value={tokenDraft}
                            onChange={(e) =>
                              setTokenDrafts((p) => ({ ...p, [row.vehicle_id]: e.target.value }))
                            }
                            autoComplete="off"
                            wrapperClassName="w-full"
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-iv-muted mb-1">
                            Car model typecode (optional)
                          </label>
                          <input
                            type="text"
                            className={inputClasses}
                            placeholder="skoda:enyaq:21:58:other"
                            value={typecodeDraft}
                            onChange={(e) =>
                              setTypecodeDrafts((p) => ({
                                ...p,
                                [row.vehicle_id]: e.target.value,
                              }))
                            }
                          />
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          className={btnPrimaryClasses}
                          disabled={
                            busy ||
                            (!tokenDraft &&
                              typecodeDraft === (row.car_model_typecode ?? ""))
                          }
                          onClick={() =>
                            saveVehicle(row.vehicle_id, {
                              ...(tokenDraft ? { token: tokenDraft } : {}),
                              car_model_typecode: typecodeDraft || null,
                            })
                          }
                        >
                          {busy ? <Loader2 size={12} className="animate-spin" /> : "Save"}
                        </button>

                        {row.has_token &&
                          (confirmClearId === row.vehicle_id ? (
                            <span className="flex items-center gap-2 text-xs">
                              <span className="text-iv-muted">Clear token?</span>
                              <button
                                type="button"
                                className="text-iv-danger hover:underline"
                                onClick={() => clearToken(row.vehicle_id)}
                              >
                                Yes
                              </button>
                              <button
                                type="button"
                                className="text-iv-muted hover:underline"
                                onClick={() => setConfirmClearId(null)}
                              >
                                No
                              </button>
                            </span>
                          ) : (
                            <button
                              type="button"
                              className="inline-flex items-center gap-1 text-xs text-iv-muted hover:text-iv-danger transition-colors"
                              onClick={() => setConfirmClearId(row.vehicle_id)}
                            >
                              <Trash2 size={12} /> Clear token
                            </button>
                          ))}

                        <button
                          type="button"
                          className="inline-flex items-center gap-1 text-xs text-iv-muted hover:text-iv-green transition-colors disabled:opacity-50"
                          disabled={busy || !row.has_token || !hasApiKey}
                          onClick={() => refreshNextCharge(row.vehicle_id)}
                        >
                          <RefreshCw size={12} /> Next charge
                        </button>

                        {row.next_charge_pct != null && (
                          <span className="inline-flex items-center rounded-full bg-iv-green/10 border border-iv-green/20 px-2.5 py-1 text-xs text-iv-green">
                            ABRP plan: charge to {row.next_charge_pct}%
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
