"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Sparkles, Crown, Zap, Users as UsersIcon, Edit2, Save, X,
  TrendingUp, DollarSign, AlertCircle, Loader2, RefreshCw, Check,
} from "lucide-react";
import { api } from "@/lib/api";

type Tier = "free" | "pro" | "team";
type TierConfig = {
  tier: Tier;
  max_questions_per_day: number;
  max_questions_per_month: number;
  model_provider: string;
  model_name: string;
  daily_cost_limit_usd: number;
  description: string;
  updated_at: string;
};
type UserAI = {
  user_id: string;
  email: string;
  display_name: string | null;
  ai_enabled: boolean;
  ai_tier: Tier;
  tier_override: Tier | null;
  ai_enabled_override: boolean | null;
  effective_max_day: number;
  effective_max_month: number;
  model_provider: string;
  model_name: string;
  used_today: number;
  used_this_month: number;
  created_at: string;
};
type UsageSummary = {
  calls_today: number;
  allowed_today: number;
  blocked_today: number;
  cost_today_usd: number;
  calls_month: number;
  cost_month_usd: number;
  calls_total: number;
  unique_users: number;
  cost_total_usd: number;
  top_users: { email: string; ai_tier: Tier; calls: number }[];
  blocked_breakdown: { blocked_reason: string; n: number }[];
};

export function AIAssistantPanel() {
  const [tiers, setTiers] = useState<TierConfig[]>([]);
  const [users, setUsers] = useState<UserAI[]>([]);
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [editingTier, setEditingTier] = useState<Tier | null>(null);
  const [savingTier, setSavingTier] = useState(false);
  const [tierFilter, setTierFilter] = useState<"all" | Tier>("all");
  const [userFilter, setUserFilter] = useState<"all" | "enabled" | "disabled">("all");

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [t, u, s] = await Promise.all([
        api.adminListAITiers(),
        api.adminListAIUsers({}),
        api.adminGetAIUsageSummary(),
      ]);
      setTiers(Array.isArray(t) ? t : []);
      setUsers(Array.isArray(u) ? u : []);
      setSummary(s || null);
    } catch (e) {
      console.error("AI panel load failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const filteredUsers = users.filter((u) => {
    if (tierFilter !== "all" && u.ai_tier !== tierFilter) return false;
    if (userFilter === "enabled" && !u.ai_enabled) return false;
    if (userFilter === "disabled" && u.ai_enabled) return false;
    return true;
  });

  const handleToggleUser = async (u: UserAI) => {
    try {
      await api.adminUpdateUserAI(u.user_id, { ai_enabled: !u.ai_enabled });
      await fetchAll();
    } catch (e) {
      console.error("toggle failed:", e);
      alert(`Failed to toggle user: ${(e as Error).message}`);
    }
  };

  const handleChangeTier = async (u: UserAI, newTier: Tier) => {
    try {
      await api.adminUpdateUserAI(u.user_id, { ai_tier: newTier });
      await fetchAll();
    } catch (e) {
      console.error("tier change failed:", e);
      alert(`Failed to change tier: ${(e as Error).message}`);
    }
  };

  const handleSaveTier = async (tier: Tier, draft: TierConfig) => {
    setSavingTier(true);
    try {
      await api.adminUpdateAITier(tier, {
        max_questions_per_day: draft.max_questions_per_day,
        max_questions_per_month: draft.max_questions_per_month,
        model_provider: draft.model_provider,
        model_name: draft.model_name,
        daily_cost_limit_usd: draft.daily_cost_limit_usd,
        description: draft.description,
      });
      setEditingTier(null);
      await fetchAll();
    } catch (e) {
      console.error("tier save failed:", e);
      alert(`Failed to save: ${(e as Error).message}`);
    } finally {
      setSavingTier(false);
    }
  };

  if (loading && !summary) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 text-iv-muted animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-iv-text flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-purple-400" />
            AI Assistant
          </h2>
          <p className="text-sm text-iv-muted mt-1">
            Premium feature gate. Configure tier limits and per-user access.
          </p>
        </div>
        <button
          onClick={fetchAll}
          disabled={loading}
          className="flex items-center gap-1.5 text-sm text-iv-muted hover:text-iv-text transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <SummaryCard
            label="Calls today"
            value={summary.calls_today}
            sub={`${summary.allowed_today} allowed · ${summary.blocked_today} blocked`}
            icon={<TrendingUp className="w-4 h-4" />}
            color="blue"
          />
          <SummaryCard
            label="Cost today"
            value={`$${summary.cost_today_usd.toFixed(4)}`}
            sub={`$${summary.cost_month_usd.toFixed(2)} this month`}
            icon={<DollarSign className="w-4 h-4" />}
            color="green"
          />
          <SummaryCard
            label="Unique users"
            value={summary.unique_users}
            sub={`${summary.calls_total} calls all-time`}
            icon={<UsersIcon className="w-4 h-4" />}
            color="purple"
          />
          <SummaryCard
            label="Blocked reasons"
            value={(summary.blocked_breakdown || []).reduce((a, b) => a + b.n, 0)}
            sub={
              (summary.blocked_breakdown || []).length
                ? (summary.blocked_breakdown || []).map((b) => `${b.blocked_reason}: ${b.n}`).join(" · ")
                : "none"
            }
            icon={<AlertCircle className="w-4 h-4" />}
            color="amber"
          />
        </div>
      )}

      {/* Tier configs */}
      <section>
        <h3 className="text-sm font-semibold text-iv-muted uppercase tracking-wide mb-3">
          Tier Configuration
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {tiers.map((t) => (
            <TierCard
              key={t.tier}
              tier={t}
              isEditing={editingTier === t.tier}
              onEdit={() => setEditingTier(t.tier)}
              onCancel={() => setEditingTier(null)}
              onSave={(draft) => handleSaveTier(t.tier, draft)}
              saving={savingTier}
            />
          ))}
        </div>
      </section>

      {/* User access list */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-iv-muted uppercase tracking-wide">
            User Access ({filteredUsers.length})
          </h3>
          <div className="flex gap-2 text-xs">
            <FilterPill active={tierFilter === "all"} onClick={() => setTierFilter("all")} label="All tiers" />
            <FilterPill active={tierFilter === "free"} onClick={() => setTierFilter("free")} label="Free" />
            <FilterPill active={tierFilter === "pro"} onClick={() => setTierFilter("pro")} label="Pro" />
            <FilterPill active={tierFilter === "team"} onClick={() => setTierFilter("team")} label="Team" />
            <span className="w-px bg-iv-border mx-1" />
            <FilterPill active={userFilter === "all"} onClick={() => setUserFilter("all")} label="All" />
            <FilterPill active={userFilter === "enabled"} onClick={() => setUserFilter("enabled")} label="On" />
            <FilterPill active={userFilter === "disabled"} onClick={() => setUserFilter("disabled")} label="Off" />
          </div>
        </div>
        <div className="bg-iv-surface/40 rounded-lg border border-iv-border/50 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-iv-surface/70 text-iv-muted text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-3 py-2">User</th>
                <th className="text-left px-3 py-2">Tier</th>
                <th className="text-left px-3 py-2">Model</th>
                <th className="text-left px-3 py-2">Today / Cap</th>
                <th className="text-left px-3 py-2">Enabled</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((u) => (
                <tr key={u.user_id} className="border-t border-iv-border/30 hover:bg-iv-surface/30">
                  <td className="px-3 py-2">
                    <div className="text-iv-text">{u.display_name || u.email}</div>
                    <div className="text-xs text-iv-muted">{u.email}</div>
                  </td>
                  <td className="px-3 py-2">
                    <select
                      value={u.ai_tier}
                      onChange={(e) => handleChangeTier(u, e.target.value as Tier)}
                      className="bg-iv-charcoal text-iv-text text-xs rounded px-2 py-1 border border-iv-border/50"
                    >
                      <option value="free">Free</option>
                      <option value="pro">Pro</option>
                      <option value="team">Team</option>
                    </select>
                    {u.tier_override && (
                      <div className="text-[10px] text-amber-400 mt-0.5">override</div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-iv-muted">
                    {u.model_provider}
                    {u.model_name && <span className="opacity-60"> / {u.model_name.slice(0, 24)}</span>}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    <span className={u.used_today >= u.effective_max_day && u.effective_max_day > 0 ? "text-amber-400" : "text-iv-text"}>
                      {u.used_today}
                    </span>
                    <span className="text-iv-muted"> / {u.effective_max_day || "∞"}</span>
                  </td>
                  <td className="px-3 py-2">
                    <button
                      onClick={() => handleToggleUser(u)}
                      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                        u.ai_enabled ? "bg-emerald-500" : "bg-iv-border"
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                          u.ai_enabled ? "translate-x-4" : "translate-x-0"
                        }`}
                      />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Top users */}
      {summary && (summary.top_users || []).length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-iv-muted uppercase tracking-wide mb-3">
            Top Users (today)
          </h3>
          <div className="bg-iv-surface/40 rounded-lg border border-iv-border/50 divide-y divide-iv-border/30">
            {(summary.top_users || []).map((u) => (
              <div key={u.email} className="flex items-center justify-between px-4 py-2 text-sm">
                <span className="text-iv-text">{u.email}</span>
                <div className="flex items-center gap-2 text-xs">
                  <TierBadge tier={u.ai_tier} />
                  <span className="text-iv-muted">{u.calls} calls</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function SummaryCard({ label, value, sub, icon, color }: {
  label: string; value: string | number; sub: string;
  icon: React.ReactNode;
  color: "blue" | "green" | "purple" | "amber";
}) {
  const colors = {
    blue: "text-blue-400 bg-blue-500/10",
    green: "text-emerald-400 bg-emerald-500/10",
    purple: "text-purple-400 bg-purple-500/10",
    amber: "text-amber-400 bg-amber-500/10",
  }[color];
  return (
    <div className="bg-iv-surface/40 border border-iv-border/50 rounded-lg p-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-iv-muted uppercase tracking-wide">{label}</span>
        <span className={`p-1.5 rounded-md ${colors}`}>{icon}</span>
      </div>
      <div className="text-xl font-semibold text-iv-text">{value}</div>
      <div className="text-xs text-iv-muted mt-0.5">{sub}</div>
    </div>
  );
}

function TierCard({ tier, isEditing, onEdit, onCancel, onSave, saving }: {
  tier: TierConfig;
  isEditing: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSave: (draft: TierConfig) => void;
  saving: boolean;
}) {
  const [draft, setDraft] = useState<TierConfig>(tier);
  // Reset draft to latest tier when entering edit mode (prevProp pattern
  // — avoids the useEffect+setState anti-pattern that causes a stale-render flash)
  const [prevEditing, setPrevEditing] = useState(isEditing);
  if (isEditing && !prevEditing) {
    setPrevEditing(true);
    setDraft(tier);
  } else if (!isEditing && prevEditing) {
    setPrevEditing(false);
  }

  const Icon = tier.tier === "free" ? Sparkles : tier.tier === "pro" ? Crown : Zap;
  const accent = {
    free: "text-slate-400 bg-slate-500/10",
    pro: "text-amber-400 bg-amber-500/10",
    team: "text-purple-400 bg-purple-500/10",
  }[tier.tier];

  return (
    <div className="bg-iv-surface/40 border border-iv-border/50 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`p-1.5 rounded-md ${accent}`}><Icon className="w-4 h-4" /></span>
          <span className="font-semibold text-iv-text capitalize">{tier.tier}</span>
        </div>
        {!isEditing ? (
          <button onClick={onEdit} className="text-iv-muted hover:text-iv-text">
            <Edit2 className="w-3.5 h-3.5" />
          </button>
        ) : (
          <div className="flex gap-1">
            <button onClick={() => onSave(draft)} disabled={saving} className="text-emerald-400 hover:text-emerald-300">
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            </button>
            <button onClick={onCancel} className="text-iv-muted hover:text-iv-text">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>

      {isEditing ? (
        <div className="space-y-2 text-xs">
          <Field label="Max / day" type="number" value={draft.max_questions_per_day} onChange={(v) => setDraft({ ...draft, max_questions_per_day: v })} />
          <Field label="Max / month" type="number" value={draft.max_questions_per_month} onChange={(v) => setDraft({ ...draft, max_questions_per_month: v })} />
          <Field label="Daily cost cap (USD)" type="number" value={draft.daily_cost_limit_usd} onChange={(v) => setDraft({ ...draft, daily_cost_limit_usd: v })} step="0.01" />
          <Field label="Model provider" value={draft.model_provider} onChange={(v) => setDraft({ ...draft, model_provider: v })} />
          <Field label="Model name" value={draft.model_name} onChange={(v) => setDraft({ ...draft, model_name: v })} />
          <Field label="Description" value={draft.description} onChange={(v) => setDraft({ ...draft, description: v })} />
        </div>
      ) : (
        <div className="space-y-1.5 text-sm">
          <Row label="Cap / day" value={tier.max_questions_per_day || "∞"} />
          <Row label="Cap / month" value={tier.max_questions_per_month || "∞"} />
          <Row label="Cost cap" value={`$${tier.daily_cost_limit_usd}/day`} />
          <Row label="Model" value={tier.model_name || tier.model_provider} mono />
          <p className="text-xs text-iv-muted mt-2 leading-relaxed">{tier.description}</p>
        </div>
      )}
    </div>
  );
}

function Field({ label, value, onChange, type = "text", step }: {
  label: string; value: string | number; onChange: (v: any) => void;
  type?: "text" | "number"; step?: string;
}) {
  return (
    <label className="block">
      <span className="text-iv-muted">{label}</span>
      <input
        type={type}
        step={step}
        value={value}
        onChange={(e) => onChange(type === "number" ? Number(e.target.value) : e.target.value)}
        className="mt-0.5 w-full bg-iv-charcoal text-iv-text rounded px-2 py-1 border border-iv-border/50 text-xs"
      />
    </label>
  );
}

function Row({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-iv-muted">{label}</span>
      <span className={`text-iv-text ${mono ? "font-mono text-[10px]" : ""}`}>{value}</span>
    </div>
  );
}

function FilterPill({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`px-2 py-0.5 rounded-full transition-colors ${
        active ? "bg-iv-text/10 text-iv-text" : "text-iv-muted hover:text-iv-text"
      }`}
    >
      {label}
    </button>
  );
}

function TierBadge({ tier }: { tier: Tier }) {
  const colors = {
    free: "bg-slate-500/20 text-slate-300",
    pro: "bg-amber-500/20 text-amber-400",
    team: "bg-purple-500/20 text-purple-400",
  }[tier];
  return <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${colors}`}>{tier}</span>;
}
