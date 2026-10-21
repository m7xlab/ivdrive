"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  ExternalLink,
  HelpCircle,
  KeyRound,
  Loader2,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { skodaApi, type SkodaPublicSettings } from "@/lib/api/integrations";
import { vehiclesApi } from "@/lib/api/vehicles";
import { PasswordInput } from "@/components/password-input";

const DOCS_URL = "https://public.api.connect.skoda-auto.cz/docs";
// Bundled locally — remote QR is blocked by CSP img-src
const KEY_QR_SRC = "/assets/myskoda-api-keys-qr.svg";
const KEY_QR_URL = "https://public.api.connect.skoda-auto.cz/docs/api-keys-qr.svg";
const APP_KEYS_URL = "https://go.skoda.eu/api-keys";

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

function HowToModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />
      <div className="glass relative w-full max-w-md rounded-2xl p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold text-iv-text flex items-center gap-2">
            <KeyRound size={18} className="text-iv-cyan" />
            Connect MyŠkoda Public API
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-iv-muted hover:text-iv-text"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        <ol className="list-decimal list-inside space-y-2 text-sm text-iv-muted leading-relaxed">
          <li>
            Open the <strong className="text-iv-text">MyŠkoda</strong> app on your phone.
          </li>
          <li>
            Go to <strong className="text-iv-text">API keys</strong> (or scan the QR below).
          </li>
          <li>
            Create a key and <strong className="text-iv-text">select the vehicles</strong> you
            want iVDrive to read.
          </li>
          <li>Copy the key and paste it here.</li>
          <li>
            Keys expire — renew in the app when iVDrive shows an expiry warning. Official
            limit: <strong className="text-iv-text">20 requests / hour / vehicle</strong>.
          </li>
        </ol>

        <div className="rounded-xl border border-iv-border bg-iv-surface p-4 flex flex-col items-center gap-3">
          {/* Official MyŠkoda API key management QR (served from /public/assets for CSP) */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={KEY_QR_SRC}
            alt="QR code to open MyŠkoda API key management"
            width={180}
            height={180}
            className="rounded-lg bg-white p-2"
          />
          <p className="text-xs text-iv-muted text-center">
            Scan with your phone to open API key management
          </p>
          <a
            href={KEY_QR_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] text-iv-muted hover:text-iv-green underline"
          >
            Open QR in browser
          </a>
        </div>

        <div className="flex flex-col gap-2">
          <a
            href={APP_KEYS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-iv-green/15 px-4 py-2.5 text-sm font-medium text-iv-green hover:bg-iv-green/25"
          >
            Open MyŠkoda API keys
            <ExternalLink size={14} />
          </a>
          <a
            href={DOCS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-iv-border px-4 py-2.5 text-sm text-iv-muted hover:text-iv-text"
          >
            Official API documentation
            <ExternalLink size={14} />
          </a>
        </div>
      </div>
    </div>
  );
}

const inputClasses =
  "w-full rounded-lg bg-iv-surface border border-iv-border px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted/60 focus:outline-none focus:border-iv-green/50 transition-colors";

const btnPrimaryClasses =
  "rounded-lg bg-iv-green/15 px-3 py-2 text-xs font-medium text-iv-green transition-colors hover:bg-iv-green/25 disabled:opacity-50 disabled:cursor-not-allowed";

export function SkodaPublicSection() {
  const [settings, setSettings] = useState<SkodaPublicSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ status: "success" | "error"; message: string } | null>(null);
  const [apiKeyDraft, setApiKeyDraft] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [editLoginFor, setEditLoginFor] = useState<string | null>(null);
  const [carEmail, setCarEmail] = useState("");
  const [carPassword, setCarPassword] = useState("");
  const [carSpin, setCarSpin] = useState("");
  const [carApiKey, setCarApiKey] = useState("");
  const [carLoginBusy, setCarLoginBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setSettings(await skodaApi.getSettings());
    } catch {
      setToast({ status: "error", message: "Failed to load Škoda API settings" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const saveKey = async (apiKey: string) => {
    setBusyId("__key__");
    try {
      const s = await skodaApi.updateSettings({ api_key: apiKey });
      setSettings(s);
      setApiKeyDraft("");
      setConfirmClear(false);
      setToast({
        status: "success",
        message: apiKey === "" ? "API key cleared" : "MyŠkoda API key saved",
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

  const setSource = async (vehicleId: string, source: string) => {
    setBusyId(vehicleId);
    try {
      const s = await skodaApi.setVehicleSource(vehicleId, source);
      setSettings(s);
      setToast({ status: "success", message: "Data source updated" });
    } catch {
      setToast({ status: "error", message: "Failed to update source" });
    } finally {
      setBusyId(null);
    }
  };

  const openCarLogin = (vehicleId: string) => {
    setEditLoginFor(vehicleId);
    setCarEmail("");
    setCarPassword("");
    setCarSpin("");
    setCarApiKey("");
  };

  const saveCarLogin = async (vehicleId: string) => {
    setCarLoginBusy(true);
    try {
      if (carEmail.trim() && carPassword) {
        await vehiclesApi.reauthenticateVehicle(vehicleId, {
          skoda_username: carEmail.trim(),
          skoda_password: carPassword,
          skoda_spin: carSpin.trim() || undefined,
        });
      }
      if (carApiKey.trim()) {
        await skodaApi.setVehicleApiKey(vehicleId, carApiKey.trim());
      }
      const s = await skodaApi.getSettings();
      setSettings(s);
      setEditLoginFor(null);
      setCarEmail("");
      setCarPassword("");
      setCarSpin("");
      setCarApiKey("");
      setToast({
        status: "success",
        message: "Saved connection for this car",
      });
    } catch (e) {
      setToast({
        status: "error",
        message:
          e instanceof Error
            ? e.message
            : "Could not save — check email, password, and API key",
      });
    } finally {
      setCarLoginBusy(false);
    }
  };

  const mintCarKey = async (vehicleId: string) => {
    setCarLoginBusy(true);
    try {
      await skodaApi.mintVehicleKey(vehicleId);
      const s = await skodaApi.getSettings();
      setSettings(s);
      setToast({ status: "success", message: "Official API key created for this car" });
    } catch (e) {
      setToast({
        status: "error",
        message: e instanceof Error ? e.message : "Could not create API key",
      });
    } finally {
      setCarLoginBusy(false);
    }
  };

  const expires = settings?.key_expires_at
    ? new Date(settings.key_expires_at).toLocaleDateString()
    : null;

  return (
    <div className="space-y-4">
      {toast && (
        <MiniToast status={toast.status} message={toast.message} onDismiss={() => setToast(null)} />
      )}
      {showHelp && <HowToModal onClose={() => setShowHelp(false)} />}

      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 text-xs text-iv-muted leading-relaxed flex-1">
          <KeyRound size={14} className="mt-0.5 flex-shrink-0 text-iv-cyan" />
          <p>
            Use the{" "}
            <a
              href={DOCS_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-iv-green hover:underline inline-flex items-center gap-0.5"
            >
              official MyŠkoda Public API
              <ExternalLink size={11} />
            </a>{" "}
            with <strong className="text-iv-text">your</strong> API key (personal use). Keeps
            working even if the unofficial connector is retired. Limit: 20 requests/hour/vehicle.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowHelp(true)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-iv-border px-3 py-2 text-xs text-iv-muted hover:text-iv-green hover:border-iv-green/40 transition-colors shrink-0"
        >
          <HelpCircle size={14} />
          How to get a key
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 size={20} className="animate-spin text-iv-muted" />
        </div>
      ) : (
        <>
          <div className="rounded-lg border border-iv-border bg-iv-surface/40 p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-iv-text">Your MyŠkoda API key</p>
                <p className="text-xs text-iv-muted mt-0.5">
                  {settings?.has_api_key
                    ? `Saved ${settings.api_key_hint}${
                        settings.expires_in_days != null
                          ? ` · expires in about ${settings.expires_in_days} day${
                              settings.expires_in_days === 1 ? "" : "s"
                            }`
                          : ""
                      }`
                    : "Not set — create one in the MyŠkoda app (valid about 3 months)"}
                </p>
              </div>
              {settings?.has_api_key && !settings?.expiry_warning && (
                <span className="inline-flex items-center rounded-full bg-iv-green/10 border border-iv-green/20 px-2.5 py-1 text-xs text-iv-green">
                  configured
                </span>
              )}
            </div>

            {settings?.expiry_warning && (
              <div className="rounded-lg border border-iv-warning/30 bg-iv-warning/10 px-3 py-2.5 text-xs text-iv-warning leading-relaxed">
                {settings.expiry_warning}
              </div>
            )}

            {settings?.last_error && (
              <div className="rounded-lg border border-iv-danger/30 bg-iv-danger/10 px-3 py-2.5 text-xs text-iv-danger leading-relaxed">
                {settings.last_error}
              </div>
            )}

            <div className="flex flex-col sm:flex-row gap-2">
              <PasswordInput
                className={inputClasses}
                placeholder={settings?.has_api_key ? "••••••  (enter to replace)" : "msk_…"}
                value={apiKeyDraft}
                onChange={(e) => setApiKeyDraft(e.target.value)}
                autoComplete="off"
                wrapperClassName="flex-1"
              />
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className={btnPrimaryClasses}
                  disabled={busyId === "__key__" || !apiKeyDraft}
                  onClick={() => saveKey(apiKeyDraft)}
                >
                  {busyId === "__key__" ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    "Save key"
                  )}
                </button>
                {settings?.has_api_key &&
                  (confirmClear ? (
                    <span className="flex items-center gap-2 text-xs">
                      <span className="text-iv-muted">Clear?</span>
                      <button
                        type="button"
                        className="text-iv-danger hover:underline"
                        onClick={() => saveKey("")}
                      >
                        Yes
                      </button>
                      <button
                        type="button"
                        className="text-iv-muted hover:underline"
                        onClick={() => setConfirmClear(false)}
                      >
                        No
                      </button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 text-xs text-iv-muted hover:text-iv-danger transition-colors"
                      onClick={() => setConfirmClear(true)}
                    >
                      <Trash2 size={12} /> Clear
                    </button>
                  ))}
              </div>
            </div>
          </div>

          <div>
            <p className="text-xs font-medium text-iv-muted uppercase tracking-wide mb-2">
              Data source per vehicle
            </p>
            <div className="space-y-2">
              {(settings?.vehicles ?? []).map((v) => (
                <div
                  key={v.vehicle_id}
                  className="rounded-lg border border-iv-border bg-iv-surface/40 p-3 space-y-3"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                    <div className="flex-1">
                      <p className="text-sm text-iv-text">{v.display_name || "Vehicle"}</p>
                      <p className="text-xs text-iv-muted">Where live data is collected from</p>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {(["auto", "login", "public"] as const).map((opt) => (
                        <button
                          key={opt}
                          type="button"
                          disabled={busyId === v.vehicle_id}
                          onClick={() => setSource(v.vehicle_id, opt)}
                          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                            (v.telemetry_source === opt ||
                              (opt === "login" && v.telemetry_source === "legacy"))
                              ? "bg-iv-green/15 text-iv-green border border-iv-green/25"
                              : "border border-iv-border text-iv-muted hover:text-iv-text"
                          }`}
                        >
                          {opt === "auto"
                            ? "Auto"
                            : opt === "login"
                              ? "MyŠkoda Login"
                              : "MyŠkoda Public API"}
                        </button>
                      ))}
                      <button
                        type="button"
                        onClick={() =>
                          editLoginFor === v.vehicle_id
                            ? setEditLoginFor(null)
                            : openCarLogin(v.vehicle_id)
                        }
                        className="rounded-lg border border-iv-border px-3 py-1.5 text-xs text-iv-cyan hover:border-iv-cyan/40"
                      >
                        {editLoginFor === v.vehicle_id ? "Close" : "Edit login"}
                      </button>
                    </div>
                  </div>

                  {editLoginFor === v.vehicle_id && (
                    <div className="rounded-lg border border-iv-border/60 bg-iv-surface/60 p-3 space-y-3">
                      <p className="text-xs text-iv-muted">
                        Connection for <strong className="text-iv-text">{v.display_name || "this car"}</strong>.
                        Leave a field blank to keep the saved value. Everything is stored encrypted
                        and applies only to this vehicle.
                      </p>

                      <div className="space-y-2">
                        <p className="text-[11px] font-medium text-iv-muted uppercase tracking-wide">
                          MyŠkoda login (optional — enables wake / lock / climate)
                        </p>
                        <div className="flex flex-col sm:flex-row gap-2">
                          <input
                            type="email"
                            autoComplete="username"
                            placeholder="MyŠkoda email"
                            value={carEmail}
                            onChange={(e) => setCarEmail(e.target.value)}
                            disabled={carLoginBusy}
                            className="flex-1 rounded-lg border border-iv-border bg-iv-surface px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted"
                          />
                          <PasswordInput
                            autoComplete="new-password"
                            placeholder="MyŠkoda password"
                            value={carPassword}
                            onChange={(e) => setCarPassword(e.target.value)}
                            disabled={carLoginBusy}
                            wrapperClassName="flex-1"
                            className="w-full rounded-lg border border-iv-border bg-iv-surface px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted"
                          />
                          <PasswordInput
                            autoComplete="off"
                            placeholder="S-PIN (optional)"
                            value={carSpin}
                            onChange={(e) => setCarSpin(e.target.value)}
                            disabled={carLoginBusy}
                            wrapperClassName="w-full sm:w-36"
                            className="w-full rounded-lg border border-iv-border bg-iv-surface px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted"
                          />
                        </div>
                      </div>

                      <div className="space-y-2">
                        <p className="text-[11px] font-medium text-iv-muted uppercase tracking-wide">
                          Official API key (for this car)
                        </p>
                        <div className="flex flex-col sm:flex-row gap-2">
                          <PasswordInput
                            autoComplete="off"
                            placeholder="msk_… (paste key or leave blank)"
                            value={carApiKey}
                            onChange={(e) => setCarApiKey(e.target.value)}
                            disabled={carLoginBusy}
                            wrapperClassName="flex-1"
                            className="w-full rounded-lg border border-iv-border bg-iv-surface px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted"
                          />
                          <button
                            type="button"
                            disabled={carLoginBusy || !carEmail.trim() || !carPassword}
                            onClick={() => mintCarKey(v.vehicle_id)}
                            title="Requires MyŠkoda email + password saved for this car"
                            className="rounded-lg border border-iv-green/30 bg-iv-green/10 px-3 py-2 text-xs font-medium text-iv-green hover:bg-iv-green/15 disabled:opacity-40"
                          >
                            Create key from login
                          </button>
                        </div>
                      </div>

                      <div className="flex gap-2">
                        <button
                          type="button"
                          disabled={carLoginBusy}
                          onClick={() => saveCarLogin(v.vehicle_id)}
                          className="rounded-lg bg-iv-green px-3 py-1.5 text-xs font-medium text-iv-bg hover:opacity-90 disabled:opacity-50"
                        >
                          {carLoginBusy ? "Saving…" : "Save"}
                        </button>
                        <button
                          type="button"
                          disabled={carLoginBusy}
                          onClick={() => setEditLoginFor(null)}
                          className="rounded-lg border border-iv-border px-3 py-1.5 text-xs text-iv-muted hover:text-iv-text"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <p className="text-[11px] text-iv-muted mt-2">
              <strong>Auto</strong> = MyŠkoda Login when connected, otherwise official Public API.{" "}
              <strong>MyŠkoda Login</strong> = advanced (wake, lock, climate).{" "}
              <strong>MyŠkoda Public API</strong> = official key only.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
