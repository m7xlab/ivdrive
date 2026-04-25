"use client";

import { useEffect, useState, useCallback } from "react";
import {
  User,
  KeyRound,
  MapPin,
  Trash2,
  Plus,
  LogOut,
  Loader2,
  CheckCircle2,
  XCircle,
  Shield,
  Car,
  Timer,
  Wifi,
  WifiOff,
  Download,
  Upload,
  Database,
  Sliders,
  Gauge,
  Monitor,
  RefreshCcw,
  Eye,
  EyeOff,
} from "lucide-react";
import Image from "next/image";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api";
import { ThemeSection } from "./theme-section";

interface SettingsVehicle {
  id: string;
  display_name: string | null;
  manufacturer: string | null;
  model: string | null;
  model_year: number | null;
  collection_enabled: boolean;
  incognito_mode: boolean;
  active_interval_seconds: number;
  parked_interval_seconds: number;
  wltp_range_km: number | null;
  country_code: string | null;
  connector_status: string | null;
  last_fetch_at: string | null;
  created_at: string;
  // Efficiency calibration
  charger_power_kw: number | null;
  ice_l_per_100km: number | null;
  uphill_kwh_per_100km_per_100m: number | null;
  downhill_kwh_per_100km_per_100m: number | null;
  speed_city_threshold_kmh: number | null;
  speed_highway_threshold_kmh: number | null;
  temp_cold_max_celsius: number | null;
  temp_optimal_min_celsius: number | null;
  temp_optimal_max_celsius: number | null;
}

interface Geofence {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  radius_meters: number;
  address: string | null;
  created_at: string;
}

function Toast({ status, message, onDismiss }: { status: "success" | "error"; message: string; onDismiss: () => void }) {
  useEffect(() => { const t = setTimeout(onDismiss, 4000); return () => clearTimeout(t); }, [onDismiss]);
  return (
    <div className={`flex items-center gap-2 rounded-lg px-4 py-3 text-sm ${status === "success" ? "bg-iv-green/10 text-iv-green" : "bg-iv-danger/10 text-iv-danger"}`}>
      {status === "success" ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
      <span className="flex-1">{message}</span>
      <button onClick={onDismiss} className="opacity-60 hover:opacity-100">×</button>
    </div>
  );
}

function SectionCard({ icon: Icon, title, children }: { icon: React.ElementType; title: string; children: React.ReactNode }) {
  return (
    <div className="glass rounded-xl overflow-hidden">
      <div className="flex items-center gap-3 border-b border-iv-border px-5 py-4">
        <Icon size={18} className="text-iv-green flex-shrink-0" />
        <h2 className="text-base font-semibold text-iv-text">{title}</h2>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

const inputClasses = "w-full rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-sm text-iv-text placeholder:text-iv-muted/60 focus:outline-none focus:border-iv-green/50 transition-colors";
const btnPrimaryClasses = "rounded-lg bg-iv-green/15 px-5 py-2.5 text-sm font-medium text-iv-green transition-colors hover:bg-iv-green/25 disabled:opacity-50 disabled:cursor-not-allowed";

function ConnectorStatusBadge({ status }: { status: string | null }) {
  if (!status) return null;
  const map: Record<string, { color: string; label: string }> = {
    active: { color: "bg-iv-green/15 text-iv-green border-iv-green/20", label: "Active" },
    pending: { color: "bg-iv-warning/15 text-iv-warning border-iv-warning/20", label: "Pending" },
    auth_failed: { color: "bg-iv-danger/15 text-iv-danger border-iv-danger/20", label: "Auth Failed" },
    token_error: { color: "bg-iv-danger/15 text-iv-danger border-iv-danger/20", label: "Token Error" },
  };
  const cfg = map[status] || { color: "bg-iv-surface text-iv-muted border-iv-border", label: status };
  return <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${cfg.color}`}>{cfg.label}</span>;
}

export default function SettingsPage() {
  const { user, logout, refreshUser } = useAuth();
  const [toast, setToast] = useState<{ status: "success" | "error"; message: string } | null>(null);

  const [displayName, setDisplayName] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);

  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [showPasswords, setShowPasswords] = useState(false);

  const [vehicles, setVehicles] = useState<SettingsVehicle[]>([]);
  const [vehiclesLoading, setVehiclesLoading] = useState(true);
  const [vehicleDeleting, setVehicleDeleting] = useState<string | null>(null);
  const [deleteModalId, setDeleteModalId] = useState<string | null>(null);
  const [reauthModalId, setReauthModalId] = useState<string | null>(null);
  const [reauthUsername, setReauthUsername] = useState("");
  const [reauthPassword, setReauthPassword] = useState("");
  const [reauthSpin, setReauthSpin] = useState("");
  const [reauthLoading, setReauthLoading] = useState(false);
  const [editingInterval, setEditingInterval] = useState<string | null>(null);
  const [editForms, setEditForms] = useState<Record<string, {
    activeInterval: number;
    parkedInterval: number;
    collectionEnabled: boolean;
    incognitoMode: boolean;
    wltpRange: string;
    countryCode: string;
  }>>({});

  const [geofences, setGeofences] = useState<Geofence[]>([]);
  const [geofencesLoading, setGeofencesLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [gfName, setGfName] = useState("");
  const [gfLat, setGfLat] = useState("");
  const [gfLon, setGfLon] = useState("");
  const [gfRadius, setGfRadius] = useState("100");
  const [gfAddress, setGfAddress] = useState("");
  const [gfSaving, setGfSaving] = useState(false);
  const [gfDeleting, setGfDeleting] = useState<string | null>(null);

  const [showDeleteAccountModal, setShowDeleteAccountModal] = useState(false);
  const [deleteAccountConfirmText, setDeleteAccountConfirmText] = useState("");
  const [accountDeleting, setAccountDeleting] = useState(false);

    const [exporting, setExporting] = useState(false);
  const [exportJobs, setExportJobs] = useState<any[]>([]);
  const [exportEnabled, setExportEnabled] = useState(false);
  const [downloadPasswords, setDownloadPasswords] = useState<Record<string, string>>({});

  const [is2FASettingLoading, setIs2FASettingLoading] = useState(false);
  const [show2FASetup, setShow2FASetup] = useState(false);
  const [twoFactorData, setTwoFactorData] = useState<{ secret: string; provisioning_uri: string; qr_code_base64: string; recovery_codes: string[] } | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState("");
  const [twoFactorPassword, setTwoFactorPassword] = useState("");
  const [show2FADisable, setShow2FADisable] = useState(false);
  const [showRecoveryCodes, setShowRecoveryCodes] = useState(false);

  const [showCommands, setShowCommands] = useState(false);
  const [calibrationExpanded, setCalibrationExpanded] = useState<string | null>(null);

  useEffect(() => { if (user) setDisplayName(user.display_name || ""); }, [user]);

  useEffect(() => {
    const stored = localStorage.getItem("ivdrive_show_commands");
    // Default to true if not set, or false? User asked to enable/disable.
    // "lets put this Command under the settings control ... user can enable of disable"
    // Given it's broken, default to false might be safer, but usually we respect existing.
    // I'll default to false as requested by the context of "hard to test... hide it".
    setShowCommands(stored === "true");
  }, []);

  const toggleCommands = () => {
    const newValue = !showCommands;
    setShowCommands(newValue);
    localStorage.setItem("ivdrive_show_commands", String(newValue));
    showToast("success", `Vehicle commands ${newValue ? "enabled" : "disabled"}`);
  };

  const loadVehicles = useCallback(async () => {
    try { const data = await api.getVehicles(); setVehicles(data); }
    finally { setVehiclesLoading(false); }
  }, []);

  const loadGeofences = useCallback(async () => {
    try { const data = await api.getGeofences(); setGeofences(data); }
    finally { setGeofencesLoading(false); }
  }, []);

    const loadExportJobs = useCallback(async () => {
    try {
      const config = await api.getExportConfig();
      setExportEnabled(config.export_enabled);
      if (config.export_enabled) {
        const data = await api.getExportStatus();
        setExportJobs(data);
      }
    } catch (e) {}
  }, []);

  useEffect(() => {
    loadVehicles();
    loadGeofences();
    loadExportJobs();
  }, [loadVehicles, loadGeofences, loadExportJobs]);

  useEffect(() => {
    const hasPending = exportJobs.some(j => j.status === "PENDING" || j.status === "PROCESSING");
    if (hasPending) {
      const timer = setInterval(loadExportJobs, 3000);
      return () => clearInterval(timer);
    }
  }, [exportJobs, loadExportJobs]);

  const showToast = (status: "success" | "error", message: string) => setToast({ status, message });

  const handleDeleteVehicle = async (id: string) => {
    setVehicleDeleting(id);
    setDeleteModalId(null);
    try { await api.deleteVehicle(id); await loadVehicles(); showToast("success", "Vehicle removed"); }
    catch (err) { showToast("error", err instanceof Error ? err.message : "Failed to delete vehicle"); }
    finally { setVehicleDeleting(null); }
  };

  const handleReauthVehicle = async (id: string) => {
    setReauthLoading(true);
    try {
      await api.reauthenticateVehicle(id, {
        skoda_username: reauthUsername.trim() || undefined,
        skoda_password: reauthPassword || undefined,
        skoda_spin: reauthSpin.trim() || undefined,
      });
      showToast("success", "Re-authenticated successfully");
      setReauthModalId(null);
      await loadVehicles();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Re-auth failed");
    } finally {
      setReauthLoading(false);
    }
  };

  const handleSaveInterval = async (id: string) => {
    try {
      const form = editForms[id];
      if (!form) return;
      const parsedWltp = form.wltpRange !== "" ? parseFloat(form.wltpRange) : null;
      await api.updateVehicle(id, {
        active_interval_seconds: form.activeInterval,
        parked_interval_seconds: form.parkedInterval,
        collection_enabled: form.collectionEnabled,
        incognito_mode: form.incognitoMode,
        wltp_range_km: parsedWltp && !isNaN(parsedWltp) ? parsedWltp : null,
        country_code: form.countryCode.trim() ? form.countryCode.trim().toUpperCase() : null,
      });
      await loadVehicles();
      setEditingInterval(null);
      showToast("success", "Vehicle settings updated");
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to update vehicle settings");
    }
  };

  const handleProfileSave = async () => {
    setProfileSaving(true);
    try { await api.updateMe({ display_name: displayName }); await refreshUser(); showToast("success", "Profile updated"); }
    catch (err) { showToast("error", err instanceof Error ? err.message : "Failed to update profile"); }
    finally { setProfileSaving(false); }
  };

  const handlePasswordChange = async () => {
    if (newPassword !== confirmPassword) { showToast("error", "Passwords do not match"); return; }
    if (newPassword.length < 8) { showToast("error", "Password must be at least 8 characters"); return; }
    setPasswordSaving(true);
    try {
      await api.changePassword(oldPassword, newPassword);
      setOldPassword(""); setNewPassword(""); setConfirmPassword("");
      showToast("success", "Password changed successfully");
    } catch (err) { showToast("error", err instanceof Error ? err.message : "Failed to change password"); }
    finally { setPasswordSaving(false); }
  };

  const handleAddGeofence = async () => {
    if (!gfName || !gfLat || !gfLon || !gfRadius) { showToast("error", "Name, latitude, longitude, and radius are required"); return; }
    setGfSaving(true);
    try {
      await api.createGeofence({ name: gfName, latitude: parseFloat(gfLat), longitude: parseFloat(gfLon), radius_meters: parseInt(gfRadius, 10), address: gfAddress || undefined });
      setGfName(""); setGfLat(""); setGfLon(""); setGfRadius("100"); setGfAddress(""); setShowAddForm(false);
      await loadGeofences(); showToast("success", "Geofence created");
    } catch (err) { showToast("error", err instanceof Error ? err.message : "Failed to create geofence"); }
    finally { setGfSaving(false); }
  };

  const handleSetup2FA = async () => {
    setIs2FASettingLoading(true);
    try {
      const data = await api.setup2FA();
      setTwoFactorData(data);
      setShow2FASetup(true);
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to load 2FA setup");
    } finally {
      setIs2FASettingLoading(false);
    }
  };

  const handleEnable2FA = async () => {
    if (!twoFactorCode || !twoFactorData) return;
    setIs2FASettingLoading(true);
    try {
      await api.enable2FA({
        code: twoFactorCode,
        secret: twoFactorData.secret,
        recovery_codes: twoFactorData.recovery_codes
      });
      showToast("success", "2FA enabled successfully");
      setShow2FASetup(false);
      setTwoFactorCode("");
      setShowRecoveryCodes(true); // Show recovery codes after success
      await refreshUser();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Invalid code");
    } finally {
      setIs2FASettingLoading(false);
    }
  };

  const handleDisable2FA = async () => {
    if (!twoFactorPassword) return;
    setIs2FASettingLoading(true);
    try {
      await api.disable2FA(twoFactorPassword);
      showToast("success", "2FA disabled successfully");
      setShow2FADisable(false);
      setTwoFactorPassword("");
      await refreshUser();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Invalid password");
    } finally {
      setIs2FASettingLoading(false);
    }
  };

  const handleDeleteGeofence = async (id: string) => {
    setGfDeleting(id);
    try { await api.deleteGeofence(id); await loadGeofences(); showToast("success", "Geofence deleted"); }
    catch (err) { showToast("error", err instanceof Error ? err.message : "Failed to delete geofence"); }
    finally { setGfDeleting(null); }
  };

  const handleDeleteAccount = async () => {
    if (deleteAccountConfirmText !== "DELETE" && deleteAccountConfirmText !== user?.email) return;
    setAccountDeleting(true);
    try {
      await api.deleteAccount();
      window.location.href = "/";
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to delete account");
      setAccountDeleting(false);
    }
  };

    const handleExport = async () => {
    setExporting(true);
    try {
      await api.exportUserData();
      showToast("success", "Export initiated! It will appear below when ready.");
      await loadExportJobs();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to generate export");
    } finally {
      setExporting(false);
    }
  };

  const handleDownload = async (jobId: string) => {
    try {
      const linkData = await api.getExportDownloadLink(jobId);
      setDownloadPasswords(prev => ({ ...prev, [jobId]: linkData.password }));
      
      const a = document.createElement("a");
      a.href = linkData.url;
      a.target = "_blank";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to get download link");
    }
  };

  const intervalLabel = (s: number) => {
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    return m < 60 ? `${m} min` : `${Math.floor(m / 60)}h ${m % 60}m`;
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold text-iv-text">Settings</h1>

      {toast && <Toast status={toast.status} message={toast.message} onDismiss={() => setToast(null)} />}

      {/* Preferences */}
      <SectionCard icon={Sliders} title="Preferences">
         <div className="flex items-center justify-between">
            <div>
               <p className="text-sm font-medium text-iv-text">Vehicle Commands (Beta)</p>
               <p className="text-xs text-iv-muted mt-0.5">Enable remote control features (Lock, Unlock, Climate, etc.)</p>
            </div>
            <label aria-label="Vehicle Commands toggle" className="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" checked={showCommands} onChange={toggleCommands} className="sr-only peer" />
              <div className="w-11 h-6 bg-iv-border peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-iv-green transition-colors"></div>
            </label>
         </div>
      </SectionCard>

      {/* Vehicles */}
      <SectionCard icon={Car} title="Vehicles">
        <div className="space-y-2">
          {vehiclesLoading ? (
            <div className="flex items-center justify-center py-8"><Loader2 size={20} className="animate-spin text-iv-muted" /></div>
          ) : vehicles.length === 0 ? (
            <div className="text-center py-8">
              <Car size={28} className="mx-auto mb-2 text-iv-muted" />
              <p className="text-sm text-iv-muted">No vehicles added yet</p>
            </div>
          ) : (
            vehicles.map((v) => (
              <div key={v.id} className="rounded-lg bg-iv-surface border border-iv-border p-3 space-y-3">

                {/* ── Top row: icon · name+badge · remove ── */}
                <div className="flex items-start gap-3">
                  <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-iv-green/10 mt-0.5">
                    <Car size={14} className="text-iv-green" />
                  </div>

                  {/* Name + badge block */}
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <p className="text-sm font-medium text-iv-text break-words">
                        {v.display_name || `${v.manufacturer || ""} ${v.model || ""}`.trim() || "Vehicle"}
                      </p>
                      <ConnectorStatusBadge status={v.connector_status} />
                    </div>
                    {/* Dates – stacked on mobile, inline on sm+ */}
                    <div className="mt-1 grid grid-cols-1 gap-0.5 sm:block">
                      <span className="text-xs text-iv-muted">
                        Added {new Date(v.created_at).toLocaleDateString()}
                      </span>
                      {v.last_fetch_at && (
                        <span className="text-xs text-iv-muted sm:before:content-['·'] sm:before:mx-1">
                          Last fetch {new Date(v.last_fetch_at).toLocaleString()}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Remove button – icon-only on mobile, icon+label on sm+ */}
                  {v.connector_status === "token_error" && (
                    <button
                      onClick={() => {
                        setReauthUsername("");
                        setReauthPassword("");
                        setReauthSpin("");
                        setReauthModalId(v.id);
                      }}
                      className="flex h-8 flex-shrink-0 items-center gap-1.5 rounded-lg px-2 text-xs font-medium text-iv-cyan hover:bg-iv-cyan/10 transition-colors"
                    >
                      <RefreshCcw size={14} />
                      <span className="hidden sm:inline">Re-Auth</span>
                    </button>
                  )}
                  <button
                    onClick={() => setDeleteModalId(v.id)}
                    disabled={vehicleDeleting === v.id}
                    className="flex h-8 flex-shrink-0 items-center gap-1.5 rounded-lg px-2 text-xs font-medium text-iv-muted hover:text-iv-danger hover:bg-iv-danger/10 transition-colors disabled:opacity-50"
                  >
                    {vehicleDeleting === v.id
                      ? <Loader2 size={14} className="animate-spin" />
                      : <Trash2 size={14} />}
                    <span className="hidden sm:inline">Remove</span>
                  </button>
                  <button
                    onClick={() => setCalibrationExpanded(v.id)}
                    className="flex h-8 flex-shrink-0 items-center gap-1.5 rounded-lg px-2 text-xs font-medium text-iv-cyan hover:bg-iv-cyan/10 transition-colors"
                    title="Efficiency Calibration"
                  >
                    <Gauge size={14} />
                    <span className="hidden sm:inline">Calibrate</span>
                  </button>
                </div>

                {/* ── Intervals row ── */}
                <div className="flex items-start gap-2 pl-0 sm:pl-11">
                  <Timer size={12} className="text-iv-muted flex-shrink-0 mt-0.5" />
                  {editingInterval === v.id ? (
                    <div className="flex flex-col gap-2 flex-1">
                      <div className="flex items-center justify-between gap-4 py-1">
                        <div className="flex-1">
                          <span className="text-sm font-medium text-iv-text block">Sync Enabled</span>
                          <span className="text-[10px] text-iv-muted block leading-tight mt-0.5">Collect background telemetry from Skoda API. Disabling pauses all data collection.</span>
                        </div>
                        <label aria-label="Sync Enabled toggle" className="relative inline-flex items-center cursor-pointer flex-shrink-0">
                          <input type="checkbox" checked={editForms[v.id]?.collectionEnabled ?? true} onChange={(e) => setEditForms(prev => ({ ...prev, [v.id]: { ...prev[v.id], collectionEnabled: e.target.checked } }))} className="sr-only peer" />
                          <div className="w-9 h-5 bg-iv-border peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-iv-green transition-colors"></div>
                        </label>
                      </div>
                      <div className="flex items-center justify-between gap-4 py-1 mb-2">
                        <div className="flex-1">
                          <span className="text-sm font-medium text-iv-text block">Incognito Mode</span>
                          <span className="text-[10px] text-iv-muted block leading-tight mt-0.5">Pause GPS/location tracking while preserving battery & charging stats.</span>
                        </div>
                        <label aria-label="Incognito Mode toggle" className="relative inline-flex items-center cursor-pointer flex-shrink-0">
                          <input type="checkbox" checked={editForms[v.id]?.incognitoMode ?? false} onChange={(e) => setEditForms(prev => ({ ...prev, [v.id]: { ...prev[v.id], incognitoMode: e.target.checked } }))} className="sr-only peer" />
                          <div className="w-9 h-5 bg-iv-border peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-iv-cyan transition-colors"></div>
                        </label>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-iv-muted w-28 flex-shrink-0">Active Telemetry</span>
                        <input type="range" min={60} max={1800} step={60} value={editForms[v.id]?.activeInterval ?? 300}
                          onChange={(e) => setEditForms(prev => ({ ...prev, [v.id]: { ...prev[v.id], activeInterval: Number(e.target.value) } }))}
                          className="flex-1 accent-iv-green min-w-0" />
                        <span className="text-xs text-iv-cyan font-mono w-14 text-right flex-shrink-0">{intervalLabel(editForms[v.id]?.activeInterval ?? 300)}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-iv-muted w-28 flex-shrink-0">Parked Check</span>
                        <input type="range" min={300} max={7200} step={300} value={editForms[v.id]?.parkedInterval ?? 1800}
                          onChange={(e) => setEditForms(prev => ({ ...prev, [v.id]: { ...prev[v.id], parkedInterval: Number(e.target.value) } }))}
                          className="flex-1 accent-iv-cyan min-w-0" />
                        <span className="text-xs text-iv-cyan font-mono w-14 text-right flex-shrink-0">{intervalLabel(editForms[v.id]?.parkedInterval ?? 1800)}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-iv-muted w-28 flex-shrink-0">WLTP Range (km)</span>
                        <input
                          type="number"
                          min={1}
                          max={2000}
                          step={1}
                          value={editForms[v.id]?.wltpRange ?? ""}
                          onChange={(e) => setEditForms(prev => ({ ...prev, [v.id]: { ...prev[v.id], wltpRange: e.target.value } }))}
                          placeholder="e.g. 510"
                          className="flex-1 min-w-0 rounded bg-iv-surface border border-iv-border px-2 py-1 text-xs text-iv-text placeholder:text-iv-muted/50 outline-none focus:border-iv-green/50"
                        />
                        <span className="text-xs text-iv-muted font-mono w-14 text-right flex-shrink-0">km</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-iv-muted w-28 flex-shrink-0">Energy Region</span>
                        <input
                          type="text"
                          maxLength={2}
                          value={editForms[v.id]?.countryCode ?? ""}
                          onChange={(e) => setEditForms(prev => ({ ...prev, [v.id]: { ...prev[v.id], countryCode: e.target.value.toUpperCase() } }))}
                          placeholder="e.g. LT"
                          className="flex-1 min-w-0 rounded bg-iv-surface border border-iv-border px-2 py-1 text-xs text-iv-text placeholder:text-iv-muted/50 outline-none focus:border-iv-green/50 uppercase"
                        />
                        <span className="text-xs text-iv-muted font-mono w-14 text-right flex-shrink-0">Code</span>
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <button onClick={() => handleSaveInterval(v.id)}
                          className="text-xs text-iv-green hover:underline">Save</button>
                        <button onClick={() => setEditingInterval(null)}
                          className="text-xs text-iv-muted hover:underline">Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <button
                      onClick={() => {
                        setEditingInterval(v.id);
                        setEditForms(prev => ({
                          ...prev,
                          [v.id]: {
                            activeInterval: v.active_interval_seconds,
                            parkedInterval: v.parked_interval_seconds,
                            collectionEnabled: v.collection_enabled ?? true,
                            incognitoMode: v.incognito_mode ?? false,
                            wltpRange: v.wltp_range_km != null ? String(v.wltp_range_km) : "",
                            countryCode: v.country_code || ""
                          }
                        }));
                      }}
                      className="text-xs text-iv-muted hover:text-iv-text transition-colors text-left"
                    >
                      {/* Stack interval pills vertically on mobile, inline on sm+ */}
                      <span className="grid grid-cols-1 gap-0.5 sm:block">
                        <span>Active: {intervalLabel(v.active_interval_seconds)}</span>
                        <span className="sm:before:content-['·'] sm:before:mx-1">
                          Parked: {intervalLabel(v.parked_interval_seconds)}
                        </span>
                        {v.wltp_range_km != null && (
                          <span className="sm:before:content-['·'] sm:before:mx-1">
                            WLTP: {v.wltp_range_km} km
                          </span>
                        )}
                        {v.country_code && (
                          <span className="sm:before:content-['·'] sm:before:mx-1">
                            Region: {v.country_code}
                          </span>
                        )}
                      </span>
                      <span className="text-iv-cyan/60 mt-1 block sm:mt-0 sm:ml-1 sm:inline">Edit</span>
                    </button>
                  )}
                </div>

                {/* ── Efficiency Calibration (inline) ── */}
                {calibrationExpanded === v.id && (
                  <div className="border-t border-iv-border/50 pt-3 space-y-3">
                    <p className="text-xs text-iv-muted">Tune analytics calculations. Pre-filled with app defaults — adjust only if needed.</p>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                      {[
                        { key: "charger_power_kw", label: "Charger Power (kW)", step: "1", min: "1", max: "350" },
                        { key: "ice_l_per_100km", label: "ICE Fuel (L/100km)", step: "0.1", min: "1", max: "20" },
                        { key: "uphill_kwh_per_100km_per_100m", label: "Uphill (kWh/100km/100m)", step: "0.01", min: "0.01", max: "2" },
                        { key: "downhill_kwh_per_100km_per_100m", label: "Downhill Regen", step: "0.01", min: "0.01", max: "2" },
                        { key: "speed_city_threshold_kmh", label: "City Speed (km/h)", step: "5", min: "10", max: "150" },
                        { key: "speed_highway_threshold_kmh", label: "Highway Speed (km/h)", step: "5", min: "50", max: "250" },
                        { key: "temp_cold_max_celsius", label: "Cold Temp (°C)", step: "1", min: "-20", max: "30" },
                        { key: "temp_optimal_min_celsius", label: "Optimal Min (°C)", step: "1", min: "-10", max: "40" },
                        { key: "temp_optimal_max_celsius", label: "Optimal Max (°C)", step: "1", min: "-10", max: "50" },
                      ].map(({ key, label, step, min, max }) => {
                        const f = (editForms[v.id] ?? {}) as unknown as Record<string, number | null>;
                        const defaults: Record<string, number> = {
                          charger_power_kw: 22.0, ice_l_per_100km: 8.0,
                          uphill_kwh_per_100km_per_100m: 0.20, downhill_kwh_per_100km_per_100m: 0.15,
                          speed_city_threshold_kmh: 50.0, speed_highway_threshold_kmh: 90.0,
                          temp_cold_max_celsius: 5.0, temp_optimal_min_celsius: 15.0, temp_optimal_max_celsius: 25.0,
                        };
                        const displayVal = (k: string, d = 2) => {
                          const val = f[k] ?? (v as unknown as Record<string, unknown>)[k] as number ?? defaults[k];
                          return val != null ? Number(val).toFixed(d) : "";
                        };
                        return (
                          <div key={key} className="flex flex-col gap-1">
                            <span className="text-iv-muted text-[10px]">{label}</span>
                            <input
                              type="number" step={step} min={min} max={max}
                              value={displayVal(key, key.includes("threshold") || key.includes("temp") ? 0 : 2)}
                              onChange={e => {
                                const val = e.target.value === "" ? null : Number(e.target.value);
                                setEditForms(prev => ({ ...prev, [v.id]: { ...prev[v.id], [key]: val } }));
                              }}
                              className="bg-iv-bg border border-iv-border rounded px-2 py-1.5 text-iv-text text-xs w-full"
                            />
                          </div>
                        );
                      })}
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={async () => {
                          const f = (editForms[v.id] ?? {}) as unknown as Record<string, number | null>;
                          const defaults: Record<string, number> = {
                            charger_power_kw: 22.0, ice_l_per_100km: 8.0,
                            uphill_kwh_per_100km_per_100m: 0.20, downhill_kwh_per_100km_per_100m: 0.15,
                            speed_city_threshold_kmh: 50.0, speed_highway_threshold_kmh: 90.0,
                            temp_cold_max_celsius: 5.0, temp_optimal_min_celsius: 15.0, temp_optimal_max_celsius: 25.0,
                          };
                          const calData: Record<string, number | null> = {};
                          Object.keys(defaults).forEach(k => {
                            const v2 = f[k];
                            if (v2 !== undefined) calData[k] = v2;
                          });
                          await api.updateVehicle(v.id, calData);
                          await loadVehicles();
                          setCalibrationExpanded(null);
                          showToast("success", "Calibration saved");
                        }}
                        className="rounded-xl bg-iv-green px-4 py-2 text-xs font-semibold text-white hover:bg-iv-green/90"
                      >Save</button>
                      <button
                        onClick={() => setCalibrationExpanded(null)}
                        className="rounded-xl border border-iv-border px-4 py-2 text-xs font-medium text-iv-muted hover:bg-iv-surface hover:text-iv-text"
                      >Cancel</button>
                    </div>
                  </div>
                )}

              </div>
            ))
          )}
        </div>
      </SectionCard>

      {/* Theme Settings */}
      <SectionCard icon={Monitor} title="Theme Preferences">
        <ThemeSection />
      </SectionCard>

      {/* Profile */}
      <SectionCard icon={User} title="Profile">
        <div className="space-y-4">
          <div>
            <label htmlFor="profile-email" className="block text-xs font-medium text-iv-muted mb-1.5">Email</label>
            <div id="profile-email" className="rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-sm text-iv-muted">{user?.email}</div>
          </div>
          <div>
            <label htmlFor="profile-display-name" className="block text-xs font-medium text-iv-muted mb-1.5">Display Name</label>
            <input id="profile-display-name" type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Your name" className={inputClasses} />
          </div>
          <div className="flex justify-end">
            <button onClick={handleProfileSave} disabled={profileSaving} className={btnPrimaryClasses}>
              {profileSaving ? <span className="flex items-center gap-2"><Loader2 size={14} className="animate-spin" />Saving...</span> : "Save Profile"}
            </button>
          </div>
        </div>
      </SectionCard>

      {/* Change Password */}
      <SectionCard icon={KeyRound} title="Change Password">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); handlePasswordChange(); }}>
          <input type="text" autoComplete="username" value={user?.email || ""} hidden readOnly />
          <div>
            <label htmlFor="pwd-current" className="block text-xs font-medium text-iv-muted mb-1.5">Current Password</label>
            <div className="relative">
              <input id="pwd-current" type={showPasswords ? "text" : "password"} value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} placeholder="Enter current password" className={inputClasses + " pr-10"} autoComplete="current-password" />
              <button type="button" onClick={() => setShowPasswords(!showPasswords)} className="absolute right-3 top-1/2 -translate-y-1/2 text-iv-muted hover:text-iv-text transition-colors">
                {showPasswords ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
          <div>
            <label htmlFor="pwd-new" className="block text-xs font-medium text-iv-muted mb-1.5">New Password</label>
            <div className="relative">
              <input id="pwd-new" type={showPasswords ? "text" : "password"} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="Enter new password" className={inputClasses + " pr-10"} autoComplete="new-password" />
              <button type="button" onClick={() => setShowPasswords(!showPasswords)} className="absolute right-3 top-1/2 -translate-y-1/2 text-iv-muted hover:text-iv-text transition-colors">
                {showPasswords ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
          <div>
            <label htmlFor="pwd-confirm" className="block text-xs font-medium text-iv-muted mb-1.5">Confirm New Password</label>
            <div className="relative">
              <input id="pwd-confirm" type={showPasswords ? "text" : "password"} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Confirm new password" className={inputClasses + " pr-10"} autoComplete="new-password" />
              <button type="button" onClick={() => setShowPasswords(!showPasswords)} className="absolute right-3 top-1/2 -translate-y-1/2 text-iv-muted hover:text-iv-text transition-colors">
                {showPasswords ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
          <div className="flex justify-end">
            <button type="submit" disabled={passwordSaving || !oldPassword || !newPassword || !confirmPassword} className={btnPrimaryClasses}>
              {passwordSaving ? <span className="flex items-center gap-2"><Loader2 size={14} className="animate-spin" />Changing...</span> : "Change Password"}
            </button>
          </div>
        </form>
      </SectionCard>

      {/* Two-Factor Authentication */}
      <SectionCard icon={Shield} title="Two-Factor Authentication (2FA)">
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-iv-text">Status: {user?.is_totp_enabled ? "Enabled" : "Disabled"}</p>
              <p className="text-xs text-iv-muted mt-0.5">
                Protect your account with an additional security layer using a mobile authenticator app.
              </p>
            </div>
            {user?.is_totp_enabled ? (
              <button
                onClick={() => setShow2FADisable(true)}
                className="rounded-lg bg-iv-danger/10 px-4 py-2 text-sm font-medium text-iv-danger transition-colors hover:bg-iv-danger/20"
              >
                Disable 2FA
              </button>
            ) : (
              <button
                onClick={handleSetup2FA}
                disabled={is2FASettingLoading}
                className={btnPrimaryClasses}
              >
                {is2FASettingLoading ? <Loader2 size={16} className="animate-spin" /> : "Enable 2FA"}
              </button>
            )}
          </div>

          {show2FASetup && twoFactorData && (
            <div className="rounded-lg bg-iv-surface border border-iv-border p-4 space-y-4">
              <div className="flex flex-col items-center gap-4 text-center">
                <p className="text-sm text-iv-text">Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.)</p>
                <div className="bg-white p-2 rounded-lg">
                  <Image src={twoFactorData.qr_code_base64} alt="2FA QR Code" width={192} height={192} />
                </div>
                <div className="w-full">
                  <p className="text-xs text-iv-muted mb-2">Or enter this secret manually:</p>
                  <code className="block bg-black/20 p-2 rounded text-iv-cyan text-sm font-mono break-all">
                    {twoFactorData.secret}
                  </code>
                </div>
              </div>
              
              <div className="p-3 bg-iv-warning/10 border border-iv-warning/30 rounded-lg">
                <p className="text-xs text-iv-warning font-medium">Important: Recovery Codes</p>
                <p className="text-[10px] text-iv-muted mt-1">
                  You will receive 10 recovery codes after successful verification. Save them in a safe place.
                </p>
              </div>

              <div>
                <label htmlFor="2fa-code" className="block text-xs font-medium text-iv-muted mb-1.5">Verification Code</label>
                <input
                  id="2fa-code"
                  type="text"
                  maxLength={6}
                  value={twoFactorCode}
                  onChange={(e) => setTwoFactorCode(e.target.value.replace(/\D/g, ""))}
                  placeholder="Enter 6-digit code"
                  className={inputClasses}
                />
              </div>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => {
                    setShow2FASetup(false);
                    setTwoFactorData(null);
                  }}
                  className="rounded-lg px-4 py-2 text-sm text-iv-muted hover:text-iv-text"
                >
                  Cancel
                </button>
                <button
                  onClick={handleEnable2FA}
                  disabled={is2FASettingLoading || twoFactorCode.length !== 6}
                  className={btnPrimaryClasses}
                >
                  {is2FASettingLoading ? "Enabling..." : "Verify & Enable"}
                </button>
              </div>
            </div>
          )}

          {showRecoveryCodes && twoFactorData && (
            <div className="rounded-lg bg-iv-green/5 border border-iv-green/20 p-4 space-y-4">
              <div className="text-center space-y-2">
                <div className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-iv-green/20 text-iv-green mb-1">
                  <CheckCircle2 size={20} />
                </div>
                <h3 className="text-sm font-bold text-iv-text">Save your recovery codes!</h3>
                <p className="text-xs text-iv-muted">
                  If you lose your phone, these codes are the ONLY way to access your account.
                </p>
              </div>
              
              <div className="grid grid-cols-2 gap-2 bg-black/20 p-4 rounded-lg font-mono text-xs">
                {twoFactorData.recovery_codes.map((code) => (
                  <div key={code} className="text-iv-cyan">{code}</div>
                ))}
              </div>

              <div className="flex justify-center">
                <button
                  onClick={() => {
                    setShowRecoveryCodes(false);
                    setTwoFactorData(null);
                  }}
                  className="text-xs font-medium text-iv-green hover:underline"
                >
                  I have saved these codes
                </button>
              </div>
            </div>
          )}

          {show2FADisable && (
            <div className="rounded-lg bg-iv-surface border border-iv-border p-4 space-y-4">
              <p className="text-sm text-iv-text">To disable 2FA, please enter your password to confirm.</p>
              <div>
                <label htmlFor="2fa-disable-pwd" className="block text-xs font-medium text-iv-muted mb-1.5">Current Password</label>
                <input
                  id="2fa-disable-pwd"
                  type="password"
                  value={twoFactorPassword}
                  onChange={(e) => setTwoFactorPassword(e.target.value)}
                  placeholder="Password"
                  className={inputClasses}
                />
              </div>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setShow2FADisable(false)}
                  className="rounded-lg px-4 py-2 text-sm text-iv-muted hover:text-iv-text"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDisable2FA}
                  disabled={is2FASettingLoading || !twoFactorPassword}
                  className="rounded-lg bg-iv-danger px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-iv-danger/90"
                >
                  {is2FASettingLoading ? "Disabling..." : "Confirm & Disable"}
                </button>
              </div>
            </div>
          )}
        </div>
      </SectionCard>

      {/* Geofences */}
      <SectionCard icon={MapPin} title="Geofences">
        <div className="space-y-4">
          {geofencesLoading ? (
            <div className="flex items-center justify-center py-8"><Loader2 size={20} className="animate-spin text-iv-muted" /></div>
          ) : geofences.length === 0 && !showAddForm ? (
            <div className="text-center py-8">
              <MapPin size={28} className="mx-auto mb-2 text-iv-muted" />
              <p className="text-sm text-iv-muted">No geofences configured</p>
            </div>
          ) : (
            <div className="space-y-2">
              {geofences.map((gf) => (
                <div key={gf.id} className="flex items-center gap-3 rounded-lg bg-iv-surface border border-iv-border p-3">
                  <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-iv-cyan/10">
                    <MapPin size={14} className="text-iv-cyan" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-iv-text truncate">{gf.name}</p>
                    <p className="text-xs text-iv-muted truncate">
                      {gf.address || `${gf.latitude.toFixed(4)}, ${gf.longitude.toFixed(4)}`} · {gf.radius_meters}m radius
                    </p>
                  </div>
                  <button onClick={() => handleDeleteGeofence(gf.id)} disabled={gfDeleting === gf.id}
                    className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-iv-muted hover:text-iv-danger hover:bg-iv-danger/10 transition-colors disabled:opacity-50">
                    {gfDeleting === gf.id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  </button>
                </div>
              ))}
            </div>
          )}

          {showAddForm ? (
            <div className="rounded-lg bg-iv-surface border border-iv-border p-4 space-y-3">
              <div>
                <label htmlFor="gf-name" className="block text-xs font-medium text-iv-muted mb-1">Name</label>
                <input id="gf-name" type="text" value={gfName} onChange={(e) => setGfName(e.target.value)} placeholder="Home, Work, etc." className={inputClasses} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="gf-lat" className="block text-xs font-medium text-iv-muted mb-1">Latitude</label>
                  <input id="gf-lat" type="number" step="any" value={gfLat} onChange={(e) => setGfLat(e.target.value)} placeholder="54.6872" className={inputClasses} />
                </div>
                <div>
                  <label htmlFor="gf-lon" className="block text-xs font-medium text-iv-muted mb-1">Longitude</label>
                  <input id="gf-lon" type="number" step="any" value={gfLon} onChange={(e) => setGfLon(e.target.value)} placeholder="25.2797" className={inputClasses} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="gf-radius" className="block text-xs font-medium text-iv-muted mb-1">Radius (meters)</label>
                  <input id="gf-radius" type="number" value={gfRadius} onChange={(e) => setGfRadius(e.target.value)} placeholder="100" className={inputClasses} />
                </div>
                <div>
                  <label htmlFor="gf-address" className="block text-xs font-medium text-iv-muted mb-1">Address (optional)</label>
                  <input id="gf-address" type="text" value={gfAddress} onChange={(e) => setGfAddress(e.target.value)} placeholder="123 Main St" className={inputClasses} />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <button onClick={() => setShowAddForm(false)} className="rounded-lg px-4 py-2 text-sm text-iv-muted hover:text-iv-text transition-colors">Cancel</button>
                <button onClick={handleAddGeofence} disabled={gfSaving} className={btnPrimaryClasses}>
                  {gfSaving ? <span className="flex items-center gap-2"><Loader2 size={14} className="animate-spin" />Creating...</span> : "Create Geofence"}
                </button>
              </div>
            </div>
          ) : (
            <button onClick={() => setShowAddForm(true)}
              className="flex items-center gap-2 rounded-lg border border-dashed border-iv-border px-4 py-2.5 text-sm text-iv-muted hover:text-iv-green hover:border-iv-green/40 transition-colors w-full justify-center">
              <Plus size={16} />
              Add Geofence
            </button>
          )}
        </div>
      </SectionCard>

      {/* Data Sovereignty */}
      {exportEnabled && (
      <SectionCard icon={Database} title="Data & Privacy">
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <p className="text-sm font-medium text-iv-text">Extract My Data</p>
              <p className="text-xs text-iv-muted mt-1 leading-relaxed">
                Download a full snapshot of your vehicle telemetry from the last 12 months. 
                This ZIP file contains a standardized JSON format that can be imported into self-hosted iVDrive instances.
              </p>
            </div>
                        <button
              onClick={handleExport}
              disabled={exporting}
              className="flex items-center gap-2 rounded-lg bg-iv-cyan/10 px-4 py-2.5 text-sm font-medium text-iv-cyan transition-colors hover:bg-iv-cyan/20 disabled:opacity-50"
            >
              {exporting ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
              {exporting ? "Requesting..." : "Request Export"}
            </button>
          </div>

          {exportJobs.length > 0 && (
            <div className="space-y-2 pt-2">
              {exportJobs.map(job => (
                <div key={job.job_id} className="flex items-center justify-between rounded-lg bg-iv-surface border border-iv-border p-3 text-sm">
                  <div>
                    <p className="font-medium text-iv-text flex items-center gap-2">
                      Export Archive
                      {job.status === "COMPLETED" && <span className="text-[10px] bg-iv-green/20 text-iv-green px-2 py-0.5 rounded uppercase font-bold">Ready</span>}
                      {(job.status === "PENDING" || job.status === "PROCESSING") && <span className="text-[10px] bg-iv-warning/20 text-iv-warning px-2 py-0.5 rounded uppercase font-bold flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> {job.status}</span>}
                      {job.status === "FAILED" && <span className="text-[10px] bg-iv-danger/20 text-iv-danger px-2 py-0.5 rounded uppercase font-bold">Failed</span>}
                    </p>
                    <p className="text-xs text-iv-muted">{new Date(job.created_at).toLocaleString()}</p>
                    
                    {downloadPasswords[job.job_id] && (
                      <p className="text-xs text-iv-warning mt-2 font-mono bg-iv-warning/10 p-1.5 rounded inline-block border border-iv-warning/20">
                        Password: {downloadPasswords[job.job_id]}
                      </p>
                    )}
                  </div>
                  
                  {job.status === "COMPLETED" && (
                    <button
                      onClick={() => handleDownload(job.job_id)}
                      className="text-iv-cyan hover:underline text-xs font-medium"
                    >
                      Download ZIP
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
          
          <div className="flex items-start justify-between gap-4 border-t border-iv-border pt-4">
            <div className="flex-1">
              <p className="text-sm font-medium text-iv-text">Restore from Snapshot</p>
              <p className="text-xs text-iv-muted mt-1 leading-relaxed">
                Coming soon: Import your historical data from a previously exported ZIP file.
              </p>
            </div>
            <button
              disabled
              className="flex items-center gap-2 rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-sm font-medium text-iv-muted cursor-not-allowed"
            >
              <Upload size={16} />
              Import
            </button>
          </div>
        </div>
      </SectionCard>
      )}

      {/* Danger Zone */}
      <SectionCard icon={Shield} title="Danger Zone">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-iv-text">Sign out</p>
            <p className="text-xs text-iv-muted mt-0.5">End your current session</p>
          </div>
          <button onClick={logout}
            className="flex items-center gap-2 rounded-lg bg-iv-danger/10 px-4 py-2.5 text-sm font-medium text-iv-danger transition-colors hover:bg-iv-danger/20">
            <LogOut size={16} />
            Logout
          </button>
        </div>
        
        <div className="mt-6 border-t border-iv-border pt-6 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-iv-danger">Delete Account</p>
            <p className="text-xs text-iv-muted mt-0.5">Permanently delete your account and all collected data</p>
          </div>
          <button onClick={() => setShowDeleteAccountModal(true)}
            className="flex items-center gap-2 rounded-lg bg-iv-danger px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-iv-danger/90">
            <Trash2 size={16} />
            Delete Account
          </button>
        </div>
      </SectionCard>

      {/* Re-authenticate modal */}
      {reauthModalId && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div role="button" tabIndex={0} aria-label="Close modal" className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => !reauthLoading && setReauthModalId(null)} onKeyDown={(e) => e.key === "Escape" && !reauthLoading && setReauthModalId(null)} />
          <div className="glass relative w-full max-w-sm rounded-2xl p-6">
            <h2 className="text-lg font-semibold text-iv-text mb-2 flex items-center gap-2"><KeyRound size={18} className="text-iv-cyan" /> Re-authenticate</h2>
            <p className="text-xs text-iv-muted mb-4">
              Your Skoda token expired. Leave fields blank to re-login with saved credentials, or provide new ones if they changed.
            </p>
            <div className="space-y-3 mb-6">
              <input type="text" placeholder="Email (optional)" value={reauthUsername} onChange={(e) => setReauthUsername(e.target.value)} disabled={reauthLoading} className="w-full rounded-lg bg-iv-surface border border-iv-border px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted/60 focus:outline-none focus:border-iv-cyan/50 transition-colors" />
              <input type="password" placeholder="Password (optional)" value={reauthPassword} onChange={(e) => setReauthPassword(e.target.value)} disabled={reauthLoading} className="w-full rounded-lg bg-iv-surface border border-iv-border px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted/60 focus:outline-none focus:border-iv-cyan/50 transition-colors" />
              <input type="password" placeholder="S-PIN (optional)" value={reauthSpin} onChange={(e) => setReauthSpin(e.target.value)} disabled={reauthLoading} className="w-full rounded-lg bg-iv-surface border border-iv-border px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted/60 focus:outline-none focus:border-iv-cyan/50 transition-colors" />
            </div>
            <div className="flex gap-3">
              <button onClick={() => setReauthModalId(null)} disabled={reauthLoading}
                className="flex-1 rounded-xl border border-iv-border px-4 py-2.5 text-sm font-medium text-iv-muted transition-colors hover:bg-iv-surface hover:text-iv-text">
                Cancel
              </button>
              <button onClick={() => handleReauthVehicle(reauthModalId)} disabled={reauthLoading}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-iv-cyan/20 px-4 py-2.5 text-sm font-semibold text-iv-cyan transition-all hover:bg-iv-cyan/30 disabled:opacity-50">
                {reauthLoading ? <Loader2 size={14} className="animate-spin" /> : "Re-login"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirmation modal */}
      {deleteModalId && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div role="button" tabIndex={0} aria-label="Close modal" className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setDeleteModalId(null)} onKeyDown={(e) => e.key === "Escape" && setDeleteModalId(null)} />
          <div className="glass relative w-full max-w-sm rounded-2xl p-6">
            <h2 className="text-lg font-semibold text-iv-text mb-2">Delete Vehicle</h2>
            <p className="text-sm text-iv-muted mb-6">
              Are you sure? All collected data will be permanently removed.
            </p>
            <div className="flex gap-3">
              <button onClick={() => setDeleteModalId(null)}
                className="flex-1 rounded-xl border border-iv-border px-4 py-2.5 text-sm font-medium text-iv-muted transition-colors hover:bg-iv-surface hover:text-iv-text">
                Cancel
              </button>
              <button onClick={() => handleDeleteVehicle(deleteModalId)}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-iv-danger px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-iv-danger/90">
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Account Modal */}
      {showDeleteAccountModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div role="button" tabIndex={0} aria-label="Close modal" className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => !accountDeleting && setShowDeleteAccountModal(false)} onKeyDown={(e) => e.key === "Escape" && !accountDeleting && setShowDeleteAccountModal(false)} />
          <div className="glass relative w-full max-w-sm rounded-2xl p-6">
            <h2 className="text-lg font-semibold text-iv-danger mb-2">Delete Account</h2>
            <p className="text-sm text-iv-text mb-4">
              This action is <span className="font-bold">irreversible</span>. All your vehicles, telemetry data, and settings will be permanently deleted.
            </p>
            <p className="text-sm text-iv-muted mb-2">
              Please type <span className="font-bold text-iv-text">DELETE</span> or your email address <span className="font-bold text-iv-text">{user?.email}</span> to confirm.
            </p>
            <input 
              type="text" 
              value={deleteAccountConfirmText}
              onChange={(e) => setDeleteAccountConfirmText(e.target.value)}
              placeholder="Confirm deletion"
              className={inputClasses + " mb-6"}
            />
            <div className="flex gap-3">
              <button onClick={() => { setShowDeleteAccountModal(false); setDeleteAccountConfirmText(""); }} disabled={accountDeleting}
                className="flex-1 rounded-xl border border-iv-border px-4 py-2.5 text-sm font-medium text-iv-muted transition-colors hover:bg-iv-surface hover:text-iv-text">
                Cancel
              </button>
              <button onClick={handleDeleteAccount} disabled={accountDeleting || (deleteAccountConfirmText !== "DELETE" && deleteAccountConfirmText !== user?.email)}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-iv-danger px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-iv-danger/90 disabled:opacity-50 disabled:cursor-not-allowed">
                {accountDeleting ? <Loader2 size={14} className="animate-spin" /> : "Delete Account"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
