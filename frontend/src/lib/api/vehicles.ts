import { apiFetch } from "./core";

export const vehiclesApi = {
  async getVehicles() {
    const res = await apiFetch("/api/v1/vehicles/");
    return res.json();
  },

  async getVehicle(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}`);
    return res.json();
  },

  async getVehicleStatus(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/status`);
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
    collection_enabled?: boolean;
    incognito_mode?: boolean;
    wltp_range_km?: number | null;
  }) {
    const res = await apiFetch("/api/v1/vehicles/", {
      method: "POST",
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async updateVehicle(
    id: string,
    data: {
      display_name?: string;
      collection_enabled?: boolean;
      incognito_mode?: boolean;
      active_interval_seconds?: number;
      parked_interval_seconds?: number;
      wltp_range_km?: number | null;
      country_code?: string | null;
      // Efficiency calibration
      charger_power_kw?: number | null;
      ice_l_per_100km?: number | null;
      uphill_kwh_per_100km_per_100m?: number | null;
      downhill_kwh_per_100km_per_100m?: number | null;
      speed_city_threshold_kmh?: number | null;
      speed_highway_threshold_kmh?: number | null;
      temp_cold_max_celsius?: number | null;
      temp_optimal_min_celsius?: number | null;
      temp_optimal_max_celsius?: number | null;
    }
  ) {
    const res = await apiFetch(`/api/v1/vehicles/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async deleteVehicle(id: string) {
    await apiFetch(`/api/v1/vehicles/${id}`, { method: "DELETE" });
  },

  async refreshVehicle(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/refresh`, { method: "POST" });
    return res.json();
  },

  async reauthenticateVehicle(id: string, body: { skoda_username?: string, skoda_password?: string, skoda_spin?: string }) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/reauthenticate`, { 
      method: "POST",
      body: JSON.stringify(body),
    });
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
    return res.json();
  },
};
