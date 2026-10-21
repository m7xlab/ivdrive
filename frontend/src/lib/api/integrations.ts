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

export interface SkodaPublicVehicle {
  vehicle_id: string;
  display_name: string | null;
  telemetry_source: string;
}

export interface SkodaPublicSettings {
  has_api_key: boolean;
  api_key_hint: string | null;
  key_expires_at: string | null;
  expires_in_days: number | null;
  expiry_warning: string | null;
  last_error: string | null;
  has_login: boolean;
  login_email_hint: string | null;
  docs_url: string;
  key_qr_url: string;
  vehicles: SkodaPublicVehicle[];
}

export const skodaApi = {
  async getSettings(): Promise<SkodaPublicSettings> {
    const res = await apiFetch("/api/v1/integrations/skoda");
    return res.json();
  },

  async updateSettings(body: { api_key?: string }): Promise<SkodaPublicSettings> {
    const res = await apiFetch("/api/v1/integrations/skoda", {
      method: "PUT",
      body: JSON.stringify(body),
    });
    return res.json();
  },

  async connectLogin(body: {
    email: string;
    password: string;
    mint_key?: boolean;
  }): Promise<SkodaPublicSettings> {
    const res = await apiFetch("/api/v1/integrations/skoda/login", {
      method: "POST",
      body: JSON.stringify(body),
    });
    return res.json();
  },

  async disconnectLogin(): Promise<SkodaPublicSettings> {
    const res = await apiFetch("/api/v1/integrations/skoda/login", {
      method: "DELETE",
    });
    return res.json();
  },

  async mintKey(): Promise<SkodaPublicSettings> {
    const res = await apiFetch("/api/v1/integrations/skoda/mint-key", {
      method: "POST",
    });
    return res.json();
  },

  async setVehicleApiKey(vehicleId: string, apiKey: string): Promise<SkodaPublicSettings> {
    const res = await apiFetch(`/api/v1/integrations/skoda/vehicles/${vehicleId}/api-key`, {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey }),
    });
    return res.json();
  },

  async mintVehicleKey(vehicleId: string): Promise<SkodaPublicSettings> {
    const res = await apiFetch(`/api/v1/integrations/skoda/vehicles/${vehicleId}/mint-key`, {
      method: "POST",
    });
    return res.json();
  },

  async setVehicleSource(
    vehicleId: string,
    telemetrySource: string,
  ): Promise<SkodaPublicSettings> {
    const res = await apiFetch(`/api/v1/integrations/skoda/vehicles/${vehicleId}`, {
      method: "PUT",
      body: JSON.stringify({ telemetry_source: telemetrySource }),
    });
    return res.json();
  },
};
