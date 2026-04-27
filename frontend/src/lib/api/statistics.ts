import { apiFetch } from "./core";

export const statisticsApi = {
  async getBatteryHistory(id: string, limit = 10000, fromDate?: string, toDate?: string) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/battery?${params.toString()}`);return res.json();
  },

  async getRangeHistory(id: string, limit = 10000, fromDate?: string, toDate?: string) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/range?${params.toString()}`);return res.json();
  },

  async getLevelsStep(id: string, limit = 10000, fromDate?: string, toDate?: string): Promise<Array<{ timestamp: string; level: number }>> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/overview/levels-step?${params.toString()}`);return res.json();
  },

  async getRangesStep(id: string, limit = 10000, fromDate?: string, toDate?: string): Promise<Array<{ timestamp: string; range_km: number }>> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/overview/ranges-step?${params.toString()}`);return res.json();
  },

  async getBatteryTemperature(id: string, limit = 10000, fromDate?: string, toDate?: string): Promise<Array<{ time: string; battery_temperature: number }>> {
    let url = `/api/v1/vehicles/${id}/overview/battery-temperature?limit=${limit}`;
    if (fromDate) url += `&from_date=${encodeURIComponent(fromDate)}`;
    if (toDate) url += `&to_date=${encodeURIComponent(toDate)}`;
    const res = await apiFetch(url);return res.json();
  },

  async getChargingPower(id: string, limit = 10000, fromDate?: string, toDate?: string): Promise<Array<{ time: string; power: number }>> {
    let url = `/api/v1/vehicles/${id}/overview/charging-power?limit=${limit}`;
    if (fromDate) url += `&from_date=${encodeURIComponent(fromDate)}`;
    if (toDate) url += `&to_date=${encodeURIComponent(toDate)}`;
    const res = await apiFetch(url);return res.json();
  },

  async getElectricConsumption(id: string, limit = 10000, fromDate?: string, toDate?: string): Promise<Array<{ time: string; consumption: number }>> {
    let url = `/api/v1/vehicles/${id}/overview/electric-consumption?limit=${limit}`;
    if (fromDate) url += `&from_date=${encodeURIComponent(fromDate)}`;
    if (toDate) url += `&to_date=${encodeURIComponent(toDate)}`;
    const res = await apiFetch(url);return res.json();
  },

  async getOutsideTemperature(id: string, limit = 10000, fromDate?: string, toDate?: string): Promise<Array<{ time: string; outside_temp_celsius: number }>> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/overview/outside-temperature?${params.toString()}`);return res.json();
  },

  async getChargingHistory(id: string, limit = 10000, fromDate?: string, toDate?: string) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/charging?${params.toString()}`);return res.json();
  },

  async getChargingSessions(id: string, limit = 10000, fromDate?: string, toDate?: string) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/charging/sessions?${params.toString()}`);return res.json();
  },

  async getTrips(id: string, limit = 10000, fromDate?: string, toDate?: string) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/trips?${params.toString()}`);return res.json();
  },

  async getTripsAnalytics(id: string, limit = 1000, fromDate?: string, toDate?: string) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/trips-analytics?${params.toString()}`);return res.json();
  },

  async getPositions(id: string, limit = 10000, fromDate?: string, toDate?: string) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/positions?${params.toString()}`);return res.json();
  },

  async getAirConditioning(id: string, limit = 50) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/air-conditioning?limit=${limit}`);return res.json();
  },

  async getMaintenance(id: string, limit = 50, fromDate?: string, toDate?: string) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/maintenance?${params.toString()}`);return res.json();
  },

  async getOdometer(id: string, limit = 10000, fromDate?: string, toDate?: string) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/odometer?${params.toString()}`);return res.json();
  },

  async getConnectionStates(id: string, limit = 50) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/connection-states?limit=${limit}`);return res.json();
  },

  async getStatistics(id: string, period = "day", limit = 30, fromDate?: string, toDate?: string) {
    const params = new URLSearchParams({ period, limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/statistics?${params.toString()}`);return res.json();
  },

  async getOverviewStateBands(id: string, opts?: { fromDate?: string; toDate?: string; limit?: number }) {
    const params = new URLSearchParams();
    if (opts?.fromDate) params.set("from_date", opts.fromDate);
    if (opts?.toDate) params.set("to_date", opts.toDate);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const res = await apiFetch(`/api/v1/vehicles/${id}/overview/state-bands?${params.toString()}`);return res.json();
  },

  async getOverviewRangeAt100(id: string, opts?: { fromDate?: string; toDate?: string; limit?: number }): Promise<Array<{ time: string; range_estimated_full: number }>> {
    const params = new URLSearchParams();
    if (opts?.fromDate) params.set("from_date", opts.fromDate);
    if (opts?.toDate) params.set("to_date", opts.toDate);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const res = await apiFetch(`/api/v1/vehicles/${id}/overview/range-at-100?${params.toString()}`);return res.json();
  },

  async getOverviewWltp(id: string): Promise<{ wltp_range_km: number | null }> {
    const res = await apiFetch(`/api/v1/vehicles/${id}/overview/wltp`);
    return res.json();
  },

  async getOverviewEfficiency(id: string, opts?: { fromDate?: string; toDate?: string; limit?: number }): Promise<Array<{ time: string; efficiency_pct: number }>> {
    const params = new URLSearchParams();
    if (opts?.fromDate) params.set("from_date", opts.fromDate);
    if (opts?.toDate) params.set("to_date", opts.toDate);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const res = await apiFetch(`/api/v1/vehicles/${id}/overview/efficiency?${params.toString()}`);return res.json();
  },

  async getAnalyticsPulse(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/pulse`);
    return res.json();
  },

  async getAnalyticsEfficiency(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/efficiency`);
    return res.json();
  },

  async getAnalyticsChargingSessions(id: string, limit: number = 10) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/charging-sessions?limit=${limit}`);
    return res.json();
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async updateChargingSession(id: string, sessionId: string | number, data: any) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/charging-sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async getTimeBudget(id: string): Promise<{ parked_seconds: number; driving_seconds: number; charging_seconds: number; ignition_seconds: number; offline_seconds: number }> {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/time-budget`);return res.json();
  },

  async getMovementStats(id: string, fromDate: string, toDate: string): Promise<{ parked_seconds: number; driving_seconds: number; charging_seconds: number; offline_seconds: number; ignition_seconds: number; total_seconds: number }> {
    const params = new URLSearchParams({ from_date: fromDate, to_date: toDate });
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/movement-stats?${params.toString()}`);return res.json();
  },

  async getVisitedLocations(id: string, limit = 2000, fromDate?: string, toDate?: string): Promise<Array<{ latitude: number; longitude: number; timestamp: string; source: string }>> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/overview/visited?${params.toString()}`);
    return res.json();
  },

  async getAdvancedAnalyticsOverview(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/advanced-overview`);
    return res.json();
  },

  async getHVACCost(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/hvac-cost`);
    return res.json();
  },

  async getHVACIsolation(id: string, opts?: { fromDate?: string; toDate?: string; limit?: number }) {
    const params = new URLSearchParams();
    if (opts?.fromDate) params.set("from_date", opts.fromDate);
    if (opts?.toDate) params.set("to_date", opts.toDate);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/hvac-isolation?${params.toString()}`);
    return res.json();
  },

  async getChargingCurveIntegralsV2(id: string, opts?: { fromDate?: string; toDate?: string }) {
    const params = new URLSearchParams();
    if (opts?.fromDate) params.set("from_date", opts.fromDate);
    if (opts?.toDate) params.set("to_date", opts.toDate);
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/charging-curve-integrals-v2?${params.toString()}`);
    return res.json();
  },

  async getElevationPenalty(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/elevation-penalty`);
    return res.json();
  },

  async getSpeedTempMatrix(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/speed-temp-matrix`);
    return res.json();
  },

  async getVampireDrain(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/vampire-drain`);
    return res.json();
  },

  async getIceTco(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/ice-tco`);
    return res.json();
  },

  async getRouteEfficiency(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/route-efficiency`);
    return res.json();
  },

  async getPredictiveSoc(id: string) {
    const res = await apiFetch(`/api/v1/vehicles/${id}/analytics/predictive-soc`);
    return res.json();
  }
};
