// Use relative path when empty so Next.js rewrites proxy /api/* to the backend (dev/Docker).
// Set NEXT_PUBLIC_API_URL only when the API is on a different host (e.g. production).
const API_BASE =
  typeof process.env.NEXT_PUBLIC_API_URL === "string" &&
  process.env.NEXT_PUBLIC_API_URL.trim() !== ""
    ? process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, "")
    : "";

export function clearTokens() {
  // Deprecated: No longer used for localStorage, backend handles HttpOnly cookies.
}

async function refreshAccessToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
    });
    return res.ok;
  } catch {
    return false;
  }
}

async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  const fetchOptions: RequestInit = {
    ...options,
    headers,
    credentials: "include",
  };

  let res = await fetch(`${API_BASE}${path}`, fetchOptions);

  if (res.status === 401) {
    // Attempt to refresh cookie
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      // Retry
      res = await fetch(`${API_BASE}${path}`, fetchOptions);
    }
  }

  return res;
}

export const api = {
  clearTokens,

  async login(email: string, password: string) {
    const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Login failed");
    const data = await res.json();
    
    return data;
  },

  async verify2FA(token2FA: string, code: string) {
    const res = await fetch(`${API_BASE}/api/v1/auth/login/verify-2fa`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ "2fa_token": token2FA, code }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "2FA verification failed");
    const tokens: TokenPair = await res.json();
    
    return tokens;
  },

  async verifyRecoveryCode(token2FA: string, recoveryCode: string) {
    const res = await fetch(`${API_BASE}/api/v1/auth/login/verify-recovery-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ "2fa_token": token2FA, recovery_code: recoveryCode }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Recovery code verification failed");
    const tokens: TokenPair = await res.json();
    
    return tokens;
  },

  async setup2FA() {
    const res = await apiFetch("/api/v1/auth/2fa/setup", { method: "POST" });
    if (!res.ok) throw new Error("Failed to start 2FA setup");
    return res.json();
  },

  async enable2FA(data: { code: string; secret: string; recovery_codes: string[] }) {
    const res = await apiFetch("/api/v1/auth/2fa/enable", {
      method: "POST",
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to enable 2FA");
    return res.json();
  },

  async disable2FA(password: string) {
    const res = await apiFetch("/api/v1/auth/2fa/disable", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to disable 2FA");
    return res.json();
  },

  async register(email: string, password: string, displayName?: string, inviteToken?: string) {
    const res = await fetch(`${API_BASE}/api/v1/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        password,
        display_name: displayName || null,
        invite_token: inviteToken || null,
      }),
    });
    if (!res.ok)
      throw new Error((await res.json()).detail || "Registration failed");
    return res.json();
  },

  async getRegistrationMode(): Promise<{ mode: string }> {
    const res = await fetch(`${API_BASE}/api/v1/auth/registration-mode`);
    if (!res.ok) return { mode: "open" };
    return res.json();
  },

  async requestInvite(email: string) {
    const res = await fetch(`${API_BASE}/api/v1/auth/invite-request`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    if (!res.ok)
      throw new Error((await res.json()).detail || "Request failed");
    return res.json();
  },

  async forgotPassword(email: string) {
    const res = await fetch(`${API_BASE}/api/v1/auth/forgot-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    if (!res.ok)
      throw new Error((await res.json()).detail || "Request failed");
    return res.json();
  },

  async resetPassword(token: string, newPassword: string) {
    const res = await fetch(`${API_BASE}/api/v1/auth/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, new_password: newPassword }),
    });
    if (!res.ok)
      throw new Error((await res.json()).detail || "Password reset failed");
    return res.json();
  },

  // ── Admin APIs ──

  async adminListInvites() {
    const res = await apiFetch("/api/v1/admin/invites");
    if (!res.ok) throw new Error("Failed to fetch invites");
    return res.json();
  },

  async adminApproveInvite(email: string) {
    const res = await apiFetch("/api/v1/admin/invites/approve", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Approve failed");
    return res.json();
  },

  async adminRejectInvite(email: string) {
    const res = await apiFetch("/api/v1/admin/invites/reject", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Reject failed");
    return res.json();
  },

  async adminRefreshUserVehicles(userId: string) {
    const res = await apiFetch(`/api/v1/admin/users/${userId}/refresh-vehicles`, { method: "POST" });
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to trigger refresh");
    return res.json();
  },

  async adminListUsers() {
    const res = await apiFetch("/api/v1/admin/users");
    if (!res.ok) throw new Error("Failed to fetch users");
    return res.json();
  },

  async adminPromoteUser(email: string) {
    const res = await apiFetch("/api/v1/admin/users/promote", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Promote failed");
    return res.json();
  },

  async adminDemoteUser(email: string) {
    const res = await apiFetch("/api/v1/admin/users/demote", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Demote failed");
    return res.json();
  },

  async adminDeleteUser(id: string) {
    const res = await apiFetch(`/api/v1/admin/users/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error((await res.json()).detail || "Delete user failed");
  },

  async adminDeleteInvite(id: string) {
    const res = await apiFetch(`/api/v1/admin/invites/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error((await res.json()).detail || "Delete invite failed");
  },

  async adminResendInvite(email: string) {
    const res = await apiFetch("/api/v1/admin/invites/resend", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Resend failed");
    return res.json();
  },

  // ── Announcement Admin APIs ──

  async adminCreateAnnouncement(data: {
    title: string;
    message: string;
    type: "info" | "success" | "warning" | "critical";
    expires_at?: string | null;
  }) {
    const res = await apiFetch("/api/v1/admin/announcements", {
      method: "POST",
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to create announcement");
    return res.json();
  },

  async adminListAnnouncements() {
    const res = await apiFetch("/api/v1/admin/announcements");
    if (!res.ok) throw new Error("Failed to fetch announcements");
    return res.json();
  },

  async adminGetStatistics() {
    const res = await apiFetch("/api/v1/admin/statistics");
    if (!res.ok) throw new Error("Failed to fetch admin statistics");
    return res.json();
  },

  async adminDeleteAnnouncement(id: string) {
    const res = await apiFetch(`/api/v1/admin/announcements/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to delete announcement");
  },

  // ── User Announcement APIs ──

  async getUserAnnouncements() {
    const res = await apiFetch("/api/v1/notifications/announcements/active");
    if (!res.ok) return [];
    return res.json();
  },

  async dismissAnnouncement(id: string) {
    const res = await apiFetch(`/api/v1/notifications/announcements/${id}/dismiss`, {
      method: "POST",
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to dismiss");
    return res.json();
  },

  async getMe() {
    const res = await apiFetch("/api/v1/auth/me");
    if (!res.ok) throw new Error("Not authenticated");
    return res.json();
  },

  // ── Data Management ──

  async exportUserData() {
    const res = await apiFetch("/api/v1/settings/export", {
      method: "POST",
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to start export");
    }
    return res.blob();
  },

  async updateMe(data: { display_name?: string }) {
    const res = await apiFetch("/api/v1/auth/me", {
      method: "PUT",
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Update failed");
    return res.json();
  },

  async changePassword(oldPassword: string, newPassword: string) {
    const res = await apiFetch("/api/v1/auth/me/password", {
      method: "PUT",
      body: JSON.stringify({
        old_password: oldPassword,
        new_password: newPassword,
      }),
    });
    if (!res.ok)
      throw new Error((await res.json()).detail || "Password change failed");
    return res.json();
  },

    async deleteAccount() {
    const res = await apiFetch("/api/v1/auth/me", { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete account");
    clearTokens();
  },

  logout() {
    clearTokens();
  },

  async getVehicles() {
    const res = await apiFetch("/api/v1/vehicles/");
    if (!res.ok) throw new Error("Failed to fetch vehicles");
    return res.json();
  },

  async getVehicle(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}`);
    if (!res.ok) throw new Error("Vehicle not found");
    return res.json();
  },

  async getVehicleStatus(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/status`);
    if (!res.ok) throw new Error("Failed to fetch status");
    return res.json();
  },

  async addVehicle(data: {
    vin: string;
    display_name?: string;
    skoda_username: string;
    skoda_password: string;
    skoda_spin?: string;
    active_interval_seconds?: number;
    parked_interval_seconds?: number;
    wltp_range_km?: number | null;
  }) {
    const res = await apiFetch("/api/v1/vehicles/", {
      method: "POST",
      body: JSON.stringify(data),
    });
    if (!res.ok)
      throw new Error((await res.json()).detail || "Failed to add vehicle");
    return res.json();
  },

  async updateVehicle(
    id: string,
    data: {
      display_name?: string;
      collection_enabled?: boolean;
      active_interval_seconds?: number;
      parked_interval_seconds?: number;
      wltp_range_km?: number | null;
      country_code?: string | null;
    }
  ) {
    const res = await apiFetch(`/api/v1/vehicles/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const errText = await res.text();
      console.error("updateVehicle 422 error details:", errText);
      throw new Error(`Failed to update vehicle: ${errText}`);
    }
    return res.json();
  },

  async deleteVehicle(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete vehicle");
  },

  async refreshVehicle(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/refresh`, { method: "POST" });
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to trigger refresh");
    return res.json();
  },

  async reauthenticateVehicle(id: string, body: { skoda_username?: string, skoda_password?: string, skoda_spin?: string }) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/reauthenticate`, { 
      method: "POST",
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to re-authenticate vehicle");
    return res.json();
  },

  async getBatteryHistory(
    id: string,
    limit = 10000,
    fromDate?: string,
    toDate?: string
  ) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/battery?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  async getRangeHistory(
    id: string,
    limit = 10000,
    fromDate?: string,
    toDate?: string
  ) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/range?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  /** Level (SoC %) step-style: first_date + last_date per segment (Grafana-style). */
  async getLevelsStep(
    id: string,
    limit = 10000,
    fromDate?: string,
    toDate?: string
  ): Promise<Array<{ timestamp: string; level: number }>> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/overview/levels-step?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  /** Range (km) step-style: first_date + last_date per segment (Grafana-style). */
  async getRangesStep(
    id: string,
    limit = 10000,
    fromDate?: string,
    toDate?: string
  ): Promise<Array<{ timestamp: string; range_km: number }>> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/overview/ranges-step?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  /** Outside temperature from air_conditioning_states. */
  
  async getBatteryTemperature(id: string, limit = 10000, fromDate?: string, toDate?: string): Promise<Array<{ time: string; battery_temperature: number }>> {
    let url = `/api/v1/vehicles/${id}/overview/battery-temperature?limit=${limit}`;
    if (fromDate) url += `&from_date=${encodeURIComponent(fromDate)}`;
    if (toDate) url += `&to_date=${encodeURIComponent(toDate)}`;
    const res = await apiFetch(url);
    if (!res.ok) return [];
    return res.json();
  },

  async getChargingPower(id: string, limit = 10000, fromDate?: string, toDate?: string): Promise<Array<{ time: string; power: number }>> {
    let url = `/api/v1/vehicles/${id}/overview/charging-power?limit=${limit}`;
    if (fromDate) url += `&from_date=${encodeURIComponent(fromDate)}`;
    if (toDate) url += `&to_date=${encodeURIComponent(toDate)}`;
    const res = await apiFetch(url);
    if (!res.ok) return [];
    return res.json();
  },

  async getElectricConsumption(id: string, limit = 10000, fromDate?: string, toDate?: string): Promise<Array<{ time: string; consumption: number }>> {
    let url = `/api/v1/vehicles/${id}/overview/electric-consumption?limit=${limit}`;
    if (fromDate) url += `&from_date=${encodeURIComponent(fromDate)}`;
    if (toDate) url += `&to_date=${encodeURIComponent(toDate)}`;
    const res = await apiFetch(url);
    if (!res.ok) return [];
    return res.json();
  },

  async getOutsideTemperature(
    id: string,
    limit = 10000,
    fromDate?: string,
    toDate?: string
  ): Promise<Array<{ time: string; outside_temp_celsius: number }>> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/overview/outside-temperature?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  async getChargingHistory(
    id: string,
    limit = 10000,
    fromDate?: string,
    toDate?: string
  ) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/charging?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  async getChargingSessions(
    id: string,
    limit = 10000,
    fromDate?: string,
    toDate?: string
  ) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/charging/sessions?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  async getTrips(
    id: string,
    limit = 10000,
    fromDate?: string,
    toDate?: string
  ) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/trips?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  async getTripsAnalytics(
    id: string,
    limit = 1000,
    fromDate?: string,
    toDate?: string
  ) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/trips-analytics?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  async getPositions(
    id: string,
    limit = 10000,
    fromDate?: string,
    toDate?: string
  ) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/positions?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  async getAirConditioning(id: string, limit = 50) {
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/air-conditioning?limit=${limit}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  async getMaintenance(
    id: string,
    limit = 50,
    fromDate?: string,
    toDate?: string
  ) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/maintenance?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  async getOdometer(
    id: string,
    limit = 10000,
    fromDate?: string,
    toDate?: string
  ) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/odometer?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  async getConnectionStates(id: string, limit = 50) {
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/connection-states?limit=${limit}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  async getStatistics(
    id: string,
    period = "day",
    limit = 30,
    fromDate?: string,
    toDate?: string
  ) {
    const params = new URLSearchParams({ period, limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/statistics?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  /** Car Overview state timeline bands (online, climatization, charging, driving). */
  async getOverviewStateBands(
    id: string,
    opts?: { fromDate?: string; toDate?: string; limit?: number }
  ) {
    const params = new URLSearchParams();
    if (opts?.fromDate) params.set("from_date", opts.fromDate);
    if (opts?.toDate) params.set("to_date", opts.toDate);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/overview/state-bands?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  /** Range extrapolated to 100% SoC (Grafana-style). */
  async getOverviewRangeAt100(
    id: string,
    opts?: { fromDate?: string; toDate?: string; limit?: number }
  ): Promise<Array<{ time: string; range_estimated_full: number }>> {
    const params = new URLSearchParams();
    if (opts?.fromDate) params.set("from_date", opts.fromDate);
    if (opts?.toDate) params.set("to_date", opts.toDate);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/overview/range-at-100?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  /** WLTP range in km for reference line. */
  async getOverviewWltp(
    id: string
  ): Promise<{ wltp_range_km: number | null }> {
    const res = await apiFetch(`/api/v1/vehicles/${id}/overview/wltp`);
    if (!res.ok) return { wltp_range_km: null };
    return res.json();
  },

  /** Efficiency % = range_estimated_full / wltp * 100 (Grafana-style). */
  async getOverviewEfficiency(
    id: string,
    opts?: { fromDate?: string; toDate?: string; limit?: number }
  ): Promise<Array<{ time: string; efficiency_pct: number }>> {
    const params = new URLSearchParams();
    if (opts?.fromDate) params.set("from_date", opts.fromDate);
    if (opts?.toDate) params.set("to_date", opts.toDate);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/overview/efficiency?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  async sendCommand(vehicleId: string, command: string, body?: object) {
    const res = await apiFetch(
      `/api/v1/vehicles/${vehicleId}/commands/${command}`,
      {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      }
    );
    if (!res.ok) throw new Error("Command failed");
    return res.json();
  },

  async getGeofences() {
    const res = await apiFetch("/api/v1/settings/geofences");
    if (!res.ok) return [];
    return res.json();
  },

  async createGeofence(data: {
    name: string;
    latitude: number;
    longitude: number;
    radius_meters: number;
    address?: string;
  }) {
    const res = await apiFetch("/api/v1/settings/geofences", {
      method: "POST",
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to create geofence");
    return res.json();
  },

  
  async getAnalyticsPulse(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/pulse`);
    if (!res.ok) throw new Error("Failed to fetch live pulse");
    return res.json();
  },

  async getAnalyticsEfficiency(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/efficiency`);
    if (!res.ok) throw new Error("Failed to fetch efficiency");
    return res.json();
  },

  async getAnalyticsChargingCosts(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/charging-costs`);
    if (!res.ok) throw new Error("Failed to fetch charging costs");
    return res.json();
  },

  async getAnalyticsChargingSessions(id: string, limit: number = 10) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/charging-sessions?limit=${limit}`);
    if (!res.ok) throw new Error("Failed to fetch charging sessions");
    return res.json();
  },

  async updateChargingSession(id: string, sessionId: string | number, data: any) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/charging-sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to update session");
    return res.json();
  },

  async deleteGeofence(id: string) {
    const res = await apiFetch(`/api/v1/settings/geofences/${id}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to delete geofence");
  },

  async getTimeBudget(
    id: string
  ): Promise<{ parked_seconds: number; driving_seconds: number; charging_seconds: number; ignition_seconds: number; offline_seconds: number }> {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/time-budget`);
    if (!res.ok) return { parked_seconds: 0, driving_seconds: 0, charging_seconds: 0, ignition_seconds: 0, offline_seconds: 0 };
    return res.json();
  },

  async getMovementStats(
    id: string,
    fromDate: string,
    toDate: string
  ): Promise<{ parked_seconds: number; driving_seconds: number; charging_seconds: number; offline_seconds: number; ignition_seconds: number; total_seconds: number }> {
    const params = new URLSearchParams({ from_date: fromDate, to_date: toDate });
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/movement-stats?${params.toString()}`);
    if (!res.ok) return { parked_seconds: 0, driving_seconds: 0, charging_seconds: 0, offline_seconds: 0, ignition_seconds: 0, total_seconds: 0 };
    return res.json();
  },

  async getVisitedLocations(
    id: string,
    limit = 2000,
    fromDate?: string,
    toDate?: string
  ): Promise<Array<{ latitude: number; longitude: number; timestamp: string; source: string }>> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/overview/visited?${params.toString()}`
    );
    if (!res.ok) return [];
    return res.json();
  },

  async getAdvancedAnalyticsOverview(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/advanced-overview`);
    if (!res.ok) throw new Error("Failed to fetch advanced overview");
    return res.json();
  },

  async reverseGeocode(latitude: number, longitude: number): Promise<{ display_name: string }> {
    const res = await apiFetch("/api/v1/geo/reverse", {
      method: "POST",
      body: JSON.stringify({ latitude, longitude }),
    });
    if (!res.ok) return { display_name: "Location" };
    return res.json();
  },
};
