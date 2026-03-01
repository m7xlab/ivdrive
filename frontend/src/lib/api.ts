// Use relative path when empty so Next.js rewrites proxy /api/* to the backend (dev/Docker).
// Set NEXT_PUBLIC_API_URL only when the API is on a different host (e.g. production).
const API_BASE =
  typeof process.env.NEXT_PUBLIC_API_URL === "string" &&
  process.env.NEXT_PUBLIC_API_URL.trim() !== ""
    ? process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, "")
    : "";

interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

function getTokens(): TokenPair | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("ivdrive_tokens");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function setTokens(tokens: TokenPair) {
  localStorage.setItem("ivdrive_tokens", JSON.stringify(tokens));
}

function clearTokens() {
  localStorage.removeItem("ivdrive_tokens");
}

async function refreshAccessToken(): Promise<string | null> {
  const tokens = getTokens();
  if (!tokens?.refresh_token) return null;

  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: tokens.refresh_token }),
    });
    if (!res.ok) {
      clearTokens();
      return null;
    }
    const newTokens: TokenPair = await res.json();
    setTokens(newTokens);
    return newTokens.access_token;
  } catch {
    clearTokens();
    return null;
  }
}

async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const tokens = getTokens();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (tokens?.access_token) {
    headers["Authorization"] = `Bearer ${tokens.access_token}`;
  }

  let res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401 && tokens?.refresh_token) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      headers["Authorization"] = `Bearer ${newToken}`;
      res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    }
  }

  return res;
}

export const api = {
  getTokens,
  setTokens,
  clearTokens,

  async login(email: string, password: string) {
    const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Login failed");
    const tokens: TokenPair = await res.json();
    setTokens(tokens);
    return tokens;
  },

  async register(email: string, password: string, displayName?: string) {
    const res = await fetch(`${API_BASE}/api/v1/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        password,
        display_name: displayName || null,
      }),
    });
    if (!res.ok)
      throw new Error((await res.json()).detail || "Registration failed");
    return res.json();
  },

  async getMe() {
    const res = await apiFetch("/api/v1/auth/me");
    if (!res.ok) throw new Error("Not authenticated");
    return res.json();
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
    }
  ) {
    const res = await apiFetch(`/api/v1/vehicles/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to update vehicle");
    return res.json();
  },

  async deleteVehicle(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete vehicle");
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

  async getMaintenance(id: string, limit = 50) {
    const res = await apiFetch(
      `/api/v1/vehicles/${id}/maintenance?limit=${limit}`
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
};
