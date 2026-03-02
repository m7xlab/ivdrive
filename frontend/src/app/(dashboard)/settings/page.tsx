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
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api";

interface SettingsVehicle {
  id: string;
  display_name: string | null;
  manufacturer: string | null;
  model: string | null;
  model_year: number | null;
  collection_enabled: boolean;
  active_interval_seconds: number;
  parked_interval_seconds: number;
  connector_status: string | null;
  last_fetch_at: string | null;
  created_at: string;
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

  const [vehicles, setVehicles] = useState<SettingsVehicle[]>([]);
  const [vehiclesLoading, setVehiclesLoading] = useState(true);
  const [vehicleDeleting, setVehicleDeleting] = useState<string | null>(null);
  const [deleteModalId, setDeleteModalId] = useState<string | null>(null);
  const [editingInterval, setEditingInterval] = useState<string | null>(null);
  const [activeInterval, setActiveInterval] = useState(300);
  const [parkedInterval, setParkedInterval] = useState(1800);

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

  const [is2FASettingLoading, setIs2FASettingLoading] = useState(false);
  const [show2FASetup, setShow2FASetup] = useState(false);
  const [twoFactorData, setTwoFactorData] = useState<{ secret: string; provisioning_uri: string; qr_code_base64: string; recovery_codes: string[] } | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState("");
  const [twoFactorPassword, setTwoFactorPassword] = useState("");
  const [show2FADisable, setShow2FADisable] = useState(false);
  const [showRecoveryCodes, setShowRecoveryCodes] = useState(false);

  useEffect(() => { if (user) setDisplayName(user.display_name || ""); }, [user]);

  const loadVehicles = useCallback(async () => {
    try { const data = await api.getVehicles(); setVehicles(data); }
    finally { setVehiclesLoading(false); }
  }, []);

  const loadGeofences = useCallback(async () => {
    try { const data = await api.getGeofences(); setGeofences(data); }
    finally { setGeofencesLoading(false); }
  }, []);

  useEffect(() => { loadVehicles(); loadGeofences(); }, [loadVehicles, loadGeofences]);

  const showToast = (status: "success" | "error", message: string) => setToast({ status, message });

  const handleDeleteVehicle = async (id: string) => {
    setVehicleDeleting(id);
    setDeleteModalId(null);
    try { await api.deleteVehicle(id); await loadVehicles(); showToast("success", "Vehicle removed"); }
    catch (err) { showToast("error", err instanceof Error ? err.message : "Failed to delete vehicle"); }
    finally { setVehicleDeleting(null); }
  };

  const handleSaveInterval = async (id: string) => {
    try {
      await api.updateVehicle(id, { active_interval_seconds: activeInterval, parked_interval_seconds: parkedInterval });
      await loadVehicles();
      setEditingInterval(null);
      showToast("success", "Polling intervals updated");
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to update intervals");
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

  const intervalLabel = (s: number) => {
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    return m < 60 ? `${m} min` : `${Math.floor(m / 60)}h ${m % 60}m`;
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold text-iv-text">Settings</h1>

      {toast && <Toast status={toast.status} message={toast.message} onDismiss={() => setToast(null)} />}

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
              <div key={v.id} className="rounded-lg bg-iv-surface border border-iv-border p-3 space-y-2">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-iv-green/10">
                    <Car size={14} className="text-iv-green" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-iv-text truncate">
                        {v.display_name || `${v.manufacturer || ""} ${v.model || ""}`.trim() || "Vehicle"}
                      </p>
                      <ConnectorStatusBadge status={v.connector_status} />
                    </div>
                    <p className="text-xs text-iv-muted">
                      Added {new Date(v.created_at).toLocaleDateString()}
                      {v.last_fetch_at && ` · Last fetch ${new Date(v.last_fetch_at).toLocaleString()}`}
                    </p>
                  </div>
                  <button onClick={() => setDeleteModalId(v.id)} disabled={vehicleDeleting === v.id}
                    className="flex h-8 items-center gap-1.5 flex-shrink-0 rounded-lg px-2 text-xs font-medium text-iv-muted hover:text-iv-danger hover:bg-iv-danger/10 transition-colors disabled:opacity-50">
                    {vehicleDeleting === v.id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                    Remove
                  </button>
                </div>

                {/* Smart Polling intervals */}
                <div className="flex items-center gap-3 pl-11">
                  <Timer size={12} className="text-iv-muted flex-shrink-0" />
                  {editingInterval === v.id ? (
                    <div className="flex flex-col gap-2 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-iv-muted w-28">Active Telemetry</span>
                        <input type="range" min={60} max={1800} step={60} value={activeInterval}
                          onChange={(e) => setActiveInterval(Number(e.target.value))}
                          className="flex-1 accent-iv-green" />
                        <span className="text-xs text-iv-cyan font-mono w-14 text-right">{intervalLabel(activeInterval)}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-iv-muted w-28">Parked Check</span>
                        <input type="range" min={300} max={7200} step={300} value={parkedInterval}
                          onChange={(e) => setParkedInterval(Number(e.target.value))}
                          className="flex-1 accent-iv-cyan" />
                        <span className="text-xs text-iv-cyan font-mono w-14 text-right">{intervalLabel(parkedInterval)}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <button onClick={() => handleSaveInterval(v.id)}
                          className="text-xs text-iv-green hover:underline">Save</button>
                        <button onClick={() => setEditingInterval(null)}
                          className="text-xs text-iv-muted hover:underline">Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <button onClick={() => { setEditingInterval(v.id); setActiveInterval(v.active_interval_seconds); setParkedInterval(v.parked_interval_seconds); }}
                      className="text-xs text-iv-muted hover:text-iv-text transition-colors">
                      Active: {intervalLabel(v.active_interval_seconds)} · Parked: {intervalLabel(v.parked_interval_seconds)} <span className="text-iv-cyan/60 ml-1">Edit</span>
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </SectionCard>

      {/* Profile */}
      <SectionCard icon={User} title="Profile">
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-iv-muted mb-1.5">Email</label>
            <div className="rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-sm text-iv-muted">{user?.email}</div>
          </div>
          <div>
            <label className="block text-xs font-medium text-iv-muted mb-1.5">Display Name</label>
            <input type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Your name" className={inputClasses} />
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
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-iv-muted mb-1.5">Current Password</label>
            <input type="password" value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} placeholder="Enter current password" className={inputClasses} />
          </div>
          <div>
            <label className="block text-xs font-medium text-iv-muted mb-1.5">New Password</label>
            <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="Enter new password" className={inputClasses} />
          </div>
          <div>
            <label className="block text-xs font-medium text-iv-muted mb-1.5">Confirm New Password</label>
            <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Confirm new password" className={inputClasses} />
          </div>
          <div className="flex justify-end">
            <button onClick={handlePasswordChange} disabled={passwordSaving || !oldPassword || !newPassword || !confirmPassword} className={btnPrimaryClasses}>
              {passwordSaving ? <span className="flex items-center gap-2"><Loader2 size={14} className="animate-spin" />Changing...</span> : "Change Password"}
            </button>
          </div>
        </div>
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
                  <img src={twoFactorData.qr_code_base64} alt="2FA QR Code" className="w-48 h-48" />
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
                <label className="block text-xs font-medium text-iv-muted mb-1.5">Verification Code</label>
                <input
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
                {twoFactorData.recovery_codes.map((code, idx) => (
                  <div key={idx} className="text-iv-cyan">{code}</div>
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
                <label className="block text-xs font-medium text-iv-muted mb-1.5">Current Password</label>
                <input
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
                <label className="block text-xs font-medium text-iv-muted mb-1">Name</label>
                <input type="text" value={gfName} onChange={(e) => setGfName(e.target.value)} placeholder="Home, Work, etc." className={inputClasses} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-iv-muted mb-1">Latitude</label>
                  <input type="number" step="any" value={gfLat} onChange={(e) => setGfLat(e.target.value)} placeholder="54.6872" className={inputClasses} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-iv-muted mb-1">Longitude</label>
                  <input type="number" step="any" value={gfLon} onChange={(e) => setGfLon(e.target.value)} placeholder="25.2797" className={inputClasses} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-iv-muted mb-1">Radius (meters)</label>
                  <input type="number" value={gfRadius} onChange={(e) => setGfRadius(e.target.value)} placeholder="100" className={inputClasses} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-iv-muted mb-1">Address (optional)</label>
                  <input type="text" value={gfAddress} onChange={(e) => setGfAddress(e.target.value)} placeholder="123 Main St" className={inputClasses} />
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
      </SectionCard>

      {/* Delete confirmation modal */}
      {deleteModalId && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setDeleteModalId(null)} />
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
    </div>
  );
}
