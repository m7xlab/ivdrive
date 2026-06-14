import { apiFetch } from "./core";

export const adminApi = {
  async adminListInvites() {
    const res = await apiFetch("/api/v1/admin/invites");
    return res.json();
  },

  async adminApproveInvite(email: string) {
    const res = await apiFetch("/api/v1/admin/invites/approve", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    return res.json();
  },

  async adminRejectInvite(email: string) {
    const res = await apiFetch("/api/v1/admin/invites/reject", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    return res.json();
  },

  async adminRefreshUserVehicles(userId: string) {
    const res = await apiFetch(`/api/v1/admin/users/${userId}/refresh-vehicles`, { method: "POST" });
    return res.json();
  },

  async adminListUsers() {
    const res = await apiFetch("/api/v1/admin/users");
    return res.json();
  },

  async adminPromoteUser(email: string) {
    const res = await apiFetch("/api/v1/admin/users/promote", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    return res.json();
  },

  async adminDemoteUser(email: string) {
    const res = await apiFetch("/api/v1/admin/users/demote", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    return res.json();
  },

  async adminDeleteUser(id: string) {
    await apiFetch(`/api/v1/admin/users/${id}`, { method: "DELETE" });
  },

  async adminDeleteInvite(id: string) {
    await apiFetch(`/api/v1/admin/invites/${id}`, { method: "DELETE" });
  },

  async adminResendInvite(email: string) {
    const res = await apiFetch("/api/v1/admin/invites/resend", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    return res.json();
  },

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
    return res.json();
  },

  async adminListAnnouncements() {
    const res = await apiFetch("/api/v1/admin/announcements");
    return res.json();
  },

  async adminGetStatistics() {
    const res = await apiFetch("/api/v1/admin/statistics");
    return res.json();
  },

  async adminDeleteAnnouncement(id: string) {
    await apiFetch(`/api/v1/admin/announcements/${id}`, { method: "DELETE" });
  },

  // ── AI Assistant premium feature ─────────────────────────────────────────
  async adminListAITiers() {
    const res = await apiFetch("/api/v1/admin/ai/tier-configs");
    return res.json();
  },
  async adminUpdateAITier(tier: string, updates: {
    max_questions_per_day?: number;
    max_questions_per_month?: number;
    model_provider?: string;
    model_name?: string;
    daily_cost_limit_usd?: number;
    description?: string;
  }) {
    const res = await apiFetch(`/api/v1/admin/ai/tier-configs/${tier}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    });
    return res.json();
  },
  async adminListAIUsers(filters: { tier?: string; enabled?: boolean } = {}) {
    const qs = new URLSearchParams();
    if (filters.tier) qs.set("tier", filters.tier);
    if (filters.enabled !== undefined) qs.set("enabled", String(filters.enabled));
    const res = await apiFetch(`/api/v1/admin/ai/users${qs.toString() ? `?${qs}` : ""}`);
    return res.json();
  },
  async adminUpdateUserAI(userId: string, updates: {
    ai_enabled?: boolean;
    ai_tier?: "free" | "pro" | "team";
    max_questions_per_day?: number | null;
    max_questions_per_month?: number | null;
    model_provider?: string | null;
    model_name?: string | null;
    note?: string | null;
  }) {
    const res = await apiFetch(`/api/v1/admin/ai/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    });
    return res.json();
  },
  async adminGetAIUsageSummary() {
    const res = await apiFetch("/api/v1/admin/ai/usage/summary");
    return res.json();
  },
  async adminGetAIUsage(filters: {
    user_id?: string; user_email?: string; blocked_only?: boolean;
    from_date?: string; to_date?: string; limit?: number;
  } = {}) {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") qs.set(k, String(v)); });
    const res = await apiFetch(`/api/v1/admin/ai/usage${qs.toString() ? `?${qs}` : ""}`);
    return res.json();
  },

  // ── RAG embeddings: status + manual backfill ─────────────────────────────
  async adminGetAIEmbeddingStatus() {
    const res = await apiFetch("/api/v1/admin/ai/embeddings/status");
    return res.json();
  },
  async adminBackfillAIEmbeddings(mode: "missing" | "all" = "missing") {
    const res = await apiFetch("/api/v1/admin/ai/embeddings/backfill", {
      method: "POST",
      body: JSON.stringify({ mode }),
    });
    return res.json();
  },
};
