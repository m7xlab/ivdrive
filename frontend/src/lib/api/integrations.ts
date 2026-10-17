import { apiFetch } from "./core";

export interface AbrpConnection {
  vehicle_id: string;
  display_name: string | null;
  enabled: boolean;
  has_token: boolean;
  token_hint: string | null;
  car_model_typecode: string | null;
  last_sent_at: string | null;
  last_error_text: string | null;
  consecutive_failures: number;
  next_charge_pct: number | null;
  next_charge_fetched_at: string | null;
}

export interface AbrpSettings {
  has_api_key: boolean;
  api_key_hint: string | null;
  connections: AbrpConnection[];
}

export interface AbrpNextCharge {
  vehicle_id: string;
  next_charge_pct: number | null;
  fetched_at: string | null;
  error: string | null;
}

export interface AbrpConnectionUpdate {
  enabled?: boolean;
  token?: string;
  car_model_typecode?: string | null;
}

export interface AbrpSettingsUpdate {
  /** Empty string clears the stored key. */
  api_key?: string;
}

export const integrationsApi = {
  async getAbrp(): Promise<AbrpSettings> {
    const res = await apiFetch("/api/v1/integrations/abrp");
    return res.json();
  },

  async updateAbrpSettings(body: AbrpSettingsUpdate): Promise<AbrpSettings> {
    const res = await apiFetch("/api/v1/integrations/abrp", {
      method: "PUT",
      body: JSON.stringify(body),
    });
    return res.json();
  },

  async upsertAbrpVehicle(
    vehicleId: string,
    body: AbrpConnectionUpdate,
  ): Promise<AbrpSettings> {
    const res = await apiFetch(`/api/v1/integrations/abrp/vehicles/${vehicleId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    return res.json();
  },

  async clearAbrpToken(vehicleId: string): Promise<AbrpSettings> {
    const res = await apiFetch(`/api/v1/integrations/abrp/vehicles/${vehicleId}/token`, {
      method: "DELETE",
    });
    return res.json();
  },

  async getNextCharge(vehicleId: string): Promise<AbrpNextCharge> {
    const res = await apiFetch(`/api/v1/integrations/abrp/vehicles/${vehicleId}/next-charge`);
    return res.json();
  },

  async refreshNextCharge(vehicleId: string): Promise<AbrpNextCharge> {
    const res = await apiFetch(
      `/api/v1/integrations/abrp/vehicles/${vehicleId}/next-charge`,
      { method: "POST" },
    );
    return res.json();
  },
};
