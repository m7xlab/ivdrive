"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { format, parseISO } from "date-fns";
import { Plug, Zap, Banknote, Edit, X } from "lucide-react";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";

interface ChargingPlan {
  id: string;
  name: string;
  plan_type: string;
}

interface SuggestCost {
  plan_id: string | null;
  plan_name: string | null;
  plan_type: string | null;
  suggested_provider_name: string | null;
  suggested_cost_eur: number | null;
  reason: string;
  remaining_kwh: number | null;
  allotment_kwh: number | null;
  matched_by: string | null;
}

function suggestionNote(s: SuggestCost | null): string | null {
  if (!s?.plan_name) return null;
  if (s.reason === "within_allotment") {
    const left = s.remaining_kwh != null ? ` · ${s.remaining_kwh} kWh remaining` : "";
    return `Suggested from ${s.plan_name} (within allotment${left})`;
  }
  if (s.reason === "overage") return `Suggested from ${s.plan_name} (overage)`;
  if (s.reason === "per_kwh") return `Suggested from ${s.plan_name} (per kWh)`;
  if (s.reason === "before_start") return `${s.plan_name} does not apply before its start date`;
  if (s.matched_by === "geofence") return `Matched ${s.plan_name} by location`;
  return `Suggested from ${s.plan_name}`;
}

export function ChargingSessionsDashboard({ vehicleId }: { vehicleId: string }) {
  const { currency, fromEur, toEur, formatMoneyFromEur } = useLocale();
  const [sessions, setSessions] = useState<any[]>([]);
  const [plans, setPlans] = useState<ChargingPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingSession, setEditingSession] = useState<any>(null);
  const editingIdRef = useRef<string | number | null>(null);
  const [editForm, setEditForm] = useState({
    actual_cost_eur: "",
    energy_kwh: "",
    provider_name: "",
    charging_plan_id: "",
  });
  const [suggestion, setSuggestion] = useState<SuggestCost | null>(null);

  const fetchSessions = async () => {
    try {
      const data = await api.getAnalyticsChargingSessions(vehicleId, 10);
      setSessions(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, [vehicleId]);

  useEffect(() => {
    api.getChargingPlans().then(setPlans).catch(() => setPlans([]));
  }, []);

  const applySuggestion = (s: SuggestCost, session: any, overwriteCost: boolean) => {
    setSuggestion(s);
    setEditForm((prev) => ({
      ...prev,
      charging_plan_id: s.plan_id || prev.charging_plan_id,
      provider_name: s.suggested_provider_name || prev.provider_name || session.provider_name || "",
      actual_cost_eur:
        overwriteCost && s.suggested_cost_eur != null
          ? String(fromEur(s.suggested_cost_eur) ?? "")
          : prev.actual_cost_eur,
    }));
  };

  const openEditor = async (session: any) => {
    const sessionId = session.id;
    editingIdRef.current = sessionId;
    setEditingSession(session);
    setSuggestion(null);
    const hasPaid = session.actual_cost_eur != null;
    setEditForm({
      actual_cost_eur: hasPaid ? String(fromEur(session.actual_cost_eur) ?? "") : "",
      energy_kwh: session.energy_kwh != null ? String(session.energy_kwh) : "",
      provider_name: session.provider_name || "",
      charging_plan_id: session.charging_plan_id || "",
    });
    try {
      const s = await api.suggestChargingSessionCost(
        vehicleId,
        session.id,
        session.charging_plan_id || undefined
      );
      if (editingIdRef.current !== sessionId) return;
      if (session.charging_plan_id) {
        setSuggestion(s);
      } else if (s.plan_id) {
        applySuggestion(s, session, !hasPaid);
      }
    } catch {
      // keep manual form
    }
  };

  const onPlanChange = async (planId: string) => {
    setEditForm((prev) => ({ ...prev, charging_plan_id: planId }));
    if (!editingSession) return;
    if (!planId) {
      setSuggestion(null);
      return;
    }
    try {
      const formKwh = Number.parseFloat(editForm.energy_kwh);
      const s = await api.suggestChargingSessionCost(
        vehicleId,
        editingSession.id,
        planId,
        Number.isFinite(formKwh) ? formKwh : undefined
      );
      applySuggestion(s, editingSession, editingSession.actual_cost_eur == null);
    } catch {
      setSuggestion(null);
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingSession) return;
    const costDisplay = Number.parseFloat(editForm.actual_cost_eur);
    const energy = Number.parseFloat(editForm.energy_kwh);
    const costEur = Number.isNaN(costDisplay) ? null : (toEur(costDisplay, 2) ?? null);
    try {
      await api.updateChargingSession(vehicleId, editingSession.id, {
        actual_cost_eur: costEur,
        energy_kwh: Number.isNaN(energy) ? (editingSession.energy_kwh ?? null) : energy,
        provider_name: editForm.provider_name || "",
        charging_plan_id: editForm.charging_plan_id || null,
      });
      setEditingSession(null);
      fetchSessions();
    } catch (err) {
      console.error("Update failed", err);
    }
  };

  if (loading) return <div className="p-8 text-center text-iv-text-muted">Loading charging history...</div>;

  const selectedPlan = plans.find((p) => p.id === editForm.charging_plan_id);

  return (
    <div className="space-y-4">
      {sessions.map((session) => {
        const hasPaid = session.actual_cost_eur != null;
        const displayCost = hasPaid ? session.actual_cost_eur : session.base_cost_eur;
        return (
          <div key={session.id} className="glass rounded-xl p-4 sm:p-5 hover:bg-iv-surface/50 transition-colors border border-iv-border">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-iv-green/10 text-iv-green">
                  <Plug className="h-5 w-5" />
                </div>
                <div>
                  <p className="font-medium text-iv-text flex items-center gap-2">
                    {session.provider_name || "Unknown Provider"}
                    <button
                      type="button"
                      onClick={() => openEditor(session)}
                      className="text-iv-text-muted hover:text-iv-cyan transition-colors"
                    >
                      <Edit className="h-4 w-4" />
                    </button>
                  </p>
                  <div className="flex items-center gap-2 text-sm text-iv-text-muted">
                    <span>{session.session_start ? format(parseISO(session.session_start), "MMM d, HH:mm") : "Unknown"}</span>
                    <span>&rarr;</span>
                    <span>{session.session_end ? format(parseISO(session.session_end), "HH:mm") : "Ongoing"}</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-6 text-right">
                <div>
                  <p className="font-semibold text-iv-text flex items-center justify-end gap-1">
                    <Zap className="h-4 w-4 text-amber-500" />
                    {session.energy_kwh != null ? `${session.energy_kwh} kWh` : "--"}
                  </p>
                  <p className="text-sm text-iv-text-muted">
                    {session.start_level}% &rarr; {session.end_level}%
                  </p>
                </div>
                <div className="hidden sm:block">
                  <p className="font-semibold text-iv-text flex items-center justify-end gap-1">
                    <Banknote className="h-4 w-4 text-emerald-500" />
                    {displayCost != null ? formatMoneyFromEur(displayCost) : "--"}
                  </p>
                  <p className="text-sm text-iv-text-muted">{hasPaid ? "Paid" : "Est. Base"}</p>
                </div>
              </div>
            </div>
          </div>
        );
      })}

      {editingSession && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl bg-iv-charcoal p-6 shadow-2xl border border-iv-border">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-bold text-iv-text">Edit Receipt Data</h3>
              <button type="button" onClick={() => setEditingSession(null)} className="text-iv-text-muted hover:text-iv-text">
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={handleEditSubmit} className="space-y-4">
              <div>
                <label htmlFor="cs-plan" className="block text-sm font-medium text-iv-text-muted mb-1">Charging plan</label>
                <select
                  id="cs-plan"
                  value={editForm.charging_plan_id}
                  onChange={(e) => onPlanChange(e.target.value)}
                  className="w-full rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-iv-text focus:border-iv-cyan focus:ring-1 focus:ring-iv-cyan outline-none transition-all"
                >
                  <option value="">Custom (no plan)</option>
                  {plans.map((p) => (
                    <option key={p.id} value={p.id}>{p.name} ({p.plan_type})</option>
                  ))}
                </select>
                {selectedPlan && (
                  <p className="mt-1 text-xs text-iv-text-muted capitalize">{selectedPlan.plan_type}</p>
                )}
                {suggestionNote(suggestion) && (
                  <p className="mt-1 text-xs text-iv-cyan">{suggestionNote(suggestion)}</p>
                )}
                <Link href="/settings" className="mt-1 inline-block text-xs text-iv-cyan hover:underline">
                  Add plan in Settings
                </Link>
              </div>
              <div>
                <label htmlFor="cs-provider-name" className="block text-sm font-medium text-iv-text-muted mb-1">Provider Name</label>
                <input
                  id="cs-provider-name"
                  type="text"
                  value={editForm.provider_name}
                  onChange={(e) => setEditForm({ ...editForm, provider_name: e.target.value })}
                  className="w-full rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-iv-text focus:border-iv-cyan focus:ring-1 focus:ring-iv-cyan outline-none transition-all"
                  placeholder="Provider name"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="cs-energy-kwh" className="block text-sm font-medium text-iv-text-muted mb-1">Energy Added (kWh)</label>
                  <input
                    id="cs-energy-kwh"
                    type="number"
                    step="0.01"
                    value={editForm.energy_kwh}
                    onChange={(e) => setEditForm({ ...editForm, energy_kwh: e.target.value })}
                    className="w-full rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-iv-text focus:border-iv-cyan focus:ring-1 focus:ring-iv-cyan outline-none transition-all"
                    placeholder="29.83"
                  />
                </div>
                <div>
                  <label htmlFor="cs-cost-eur" className="block text-sm font-medium text-iv-text-muted mb-1">Total Paid ({currency})</label>
                  <input
                    id="cs-cost-eur"
                    type="number"
                    step="0.01"
                    min="0"
                    value={editForm.actual_cost_eur}
                    onChange={(e) => setEditForm({ ...editForm, actual_cost_eur: e.target.value })}
                    className="w-full rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-iv-text focus:border-iv-cyan focus:ring-1 focus:ring-iv-cyan outline-none transition-all"
                    placeholder="0.00"
                  />
                </div>
              </div>
              <div className="mt-6 flex justify-end gap-3">
                <button type="button" onClick={() => setEditingSession(null)} className="px-4 py-2 rounded-xl text-sm font-medium text-iv-text bg-iv-surface hover:bg-iv-border transition-colors">
                  Cancel
                </button>
                <button type="submit" className="px-4 py-2 rounded-xl text-sm font-medium text-white bg-iv-cyan hover:bg-iv-cyan/90 transition-colors">
                  Save Receipt
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
