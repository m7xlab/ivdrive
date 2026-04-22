export * from "./api/index";
  async getHVACIsolation(vehicleId: string) {
    const res = await fetchClient(`/api/v1/vehicles/${vehicleId}/analytics/hvac-isolation`);
    if (!res.ok) throw new Error("Failed to fetch HVAC isolation");
    return res.json();
  },

