import { apiFetch } from "./core";

export const settingsApi = {
  async getGeofences() {
    const res = await apiFetch("/api/v1/settings/geofences");
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
    return res.json();
  },

  async deleteGeofence(id: string) {
    await apiFetch(`/api/v1/settings/geofences/${id}`, {
      method: "DELETE",
    });
  },

  async exportUserData() {
    const res = await apiFetch("/api/v1/settings/export", {
      method: "POST",
    });
    return res.json();
  },

  async getExportConfig() {
    const res = await apiFetch("/api/v1/settings/export/config", {
      method: "GET",
    });
    return res.json();
  },

  async getExportStatus() {
    const res = await apiFetch("/api/v1/settings/export/status", {
      method: "GET",
    });
    return res.json();
  },

  async getExportDownloadLink(jobId: string) {
    const res = await apiFetch(`/api/v1/settings/export/${jobId}/download`, {
      method: "GET",
    });
    return res.json();
  },

  async getUserAnnouncements() {
    try {
      const res = await apiFetch("/api/v1/notifications/announcements/active");
      return res.json();
    } catch {
      return [];
    }
  },

  async dismissAnnouncement(id: string) {
    const res = await apiFetch(`/api/v1/notifications/announcements/${id}/dismiss`, {
      method: "POST",
    });
    return res.json();
  },

  async getCurrencies(): Promise<
    Array<{
      code: string;
      name: string;
      symbol: string;
      rate_per_eur: number;
      as_of: string;
      source: string;
    }>
  > {
    const res = await apiFetch("/api/v1/settings/currencies");
    return res.json();
  },

  async getChargingPlans() {
    const res = await apiFetch("/api/v1/settings/charging-plans");
    return res.json();
  },

  async createChargingPlan(data: Record<string, unknown>) {
    const res = await apiFetch("/api/v1/settings/charging-plans", {
      method: "POST",
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async updateChargingPlan(id: string, data: Record<string, unknown>) {
    const res = await apiFetch(`/api/v1/settings/charging-plans/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async deleteChargingPlan(id: string) {
    await apiFetch(`/api/v1/settings/charging-plans/${id}`, {
      method: "DELETE",
    });
  },
};
