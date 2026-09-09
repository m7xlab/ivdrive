import { apiFetch, setAuthFlag, clearAuthFlag } from "./core";

// Define the type if needed, though we can just use any for now or inline it.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type TokenPair = any;

export const authApi = {
  async login(email: string, password: string) {
    const res = await apiFetch(`/api/v1/auth/login`, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!data.requires_2fa) setAuthFlag();
    return data;
  },

  async verify2FA(token2FA: string, code: string) {
    const res = await apiFetch(`/api/v1/auth/login/verify-2fa`, {
      method: "POST",
      body: JSON.stringify({ "2fa_token": token2FA, code }),
    });
    const tokens: TokenPair = await res.json();
    setAuthFlag();
    return tokens;
  },

  async verifyRecoveryCode(token2FA: string, recoveryCode: string) {
    const res = await apiFetch(`/api/v1/auth/login/verify-recovery-code`, {
      method: "POST",
      body: JSON.stringify({ "2fa_token": token2FA, recovery_code: recoveryCode }),
    });
    const tokens: TokenPair = await res.json();
    setAuthFlag();
    return tokens;
  },

  async setup2FA() {
    const res = await apiFetch("/api/v1/auth/2fa/setup", { method: "POST" });
    return res.json();
  },

  async enable2FA(data: { code: string; secret: string; recovery_codes: string[] }) {
    const res = await apiFetch("/api/v1/auth/2fa/enable", {
      method: "POST",
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async disable2FA(password: string) {
    const res = await apiFetch("/api/v1/auth/2fa/disable", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    return res.json();
  },

  async register(email: string, password: string, displayName?: string, inviteToken?: string) {
    const res = await apiFetch(`/api/v1/auth/register`, {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        display_name: displayName || null,
        invite_token: inviteToken || null,
      }),
    });
    setAuthFlag();
    return res.json();
  },

  async getRegistrationMode(): Promise<{ mode: string }> {
    try {
      const res = await apiFetch(`/api/v1/auth/registration-mode`);
      return res.json();
    } catch {
      return { mode: "open" };
    }
  },

  async requestInvite(email: string) {
    const res = await apiFetch(`/api/v1/auth/invite-request`, {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    return res.json();
  },

  async forgotPassword(email: string) {
    const res = await apiFetch(`/api/v1/auth/forgot-password`, {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    return res.json();
  },

  async resetPassword(token: string, newPassword: string) {
    const res = await apiFetch(`/api/v1/auth/reset-password`, {
      method: "POST",
      body: JSON.stringify({ token, new_password: newPassword }),
    });
    return res.json();
  },

  async getMe() {
    const res = await apiFetch("/api/v1/auth/me");
    return res.json();
  },

  async updateMe(data: {
    display_name?: string;
    default_currency?: string;
    unit_system?: "metric" | "uk" | "us" | "imperial";
  }) {
    const res = await apiFetch("/api/v1/auth/me", {
      method: "PUT",
      body: JSON.stringify(data),
    });
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
    return res.json();
  },

  async deleteAccount() {
    await apiFetch("/api/v1/auth/me", { method: "DELETE" });
    clearAuthFlag();
  },

  async logout() {
    try {
      await apiFetch(`/api/v1/auth/logout`, {
        method: "POST",
      });
    } catch (e) {
      console.error("Logout failed:", e);
    }
    clearAuthFlag();
  },
};
