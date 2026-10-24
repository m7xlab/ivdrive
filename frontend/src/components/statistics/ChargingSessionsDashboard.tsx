"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { format, parseISO } from "date-fns";
import { Plug, Zap, Banknote, Edit, Plus, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useLocale } from "@/lib/locale";
import { useToast } from "@/components/ui/feedback";

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
  suggested_paid_eur: number | null;
  reason: string;
  remaining_kwh: number | null;
  remaining_after_kwh: number | null;
  remaining_fee_eur: number | null;
  allotment_kwh: number | null;
  included_rate_eur: number | null;
  overage_rate_eur: number | null;
  period_fee_eur: number | null;
  matched_by: string | null;
}

function suggestionNote(
  s: SuggestCost | null,
  formatMoneyFromEur: (amount: number | null | undefined, places?: number) => string
): string | null {
  if (!s?.plan_name) return null;
  if (s.reason === "within_allotment" || s.reason === "mixed") {
    const allocated = s.suggested_cost_eur != null ? formatMoneyFromEur(s.suggested_cost_eur) : null;
    const leftKwh = s.remaining_after_kwh != null ? `${s.remaining_after_kwh} kWh left` : null;
    const leftFee = s.remaining_fee_eur != null ? `${formatMoneyFromEur(s.remaining_fee_eur)} of the period fee left` : null;
    const bits = [allocated ? `${allocated} on ${s.plan_name}` : s.plan_name, leftKwh, leftFee].filter(Boolean);
    return `${bits.join(" · ")}. Leave paid at 0 if you did not pay at the charger.`;
  }
  if (s.reason === "overage") return `${s.plan_name}: included kWh is used. Public walk-up applies to this charge.`;
  if (s.reason === "per_kwh") return `Suggested from ${s.plan_name} (per kWh)`;
  if (s.reason === "before_start") return `${s.plan_name} does not apply before its start date`;
  if (s.matched_by === "geofence") return `Matched ${s.plan_name} by location`;
  return `Suggested from ${s.plan_name}`;
}

type FormFields = {
  session_start: string;
  session_end: string;
  start_level: string;
  end_level: string;
  energy_kwh: string;
  actual_cost_eur: string;
  provider_name: string;
  charging_plan_id: string;
};

const EMPTY_FORM: FormFields = {
  session_start: "",
  session_end: "",
  start_level: "",
  end_level: "",
  energy_kwh: "",
  actual_cost_eur: "",
  provider_name: "",
  charging_plan_id: "",
};

function toDatetimeLocal(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = parseISO(iso);
  if (Number.isNaN(d.getTime())) return "";
  return format(d, "yyyy-MM-dd'T'HH:mm");
}

function parseOptionalNumber(value: string): number | null {
  const n = Number.parseFloat(value);
  return Number.isFinite(n) ? n : null;
}

function humanError(err: unknown, fallback: string): string {
  if (err instanceof ApiError && err.status === 422) return "Please check the values you entered.";
  if (err instanceof Error && err.message && err.message !== "An error occurred") return err.message;
  return fallback;
}

export function ChargingSessionsDashboard({
  vehicleId,
  onChanged,
}: {
  vehicleId: string;
  onChanged?: () => void;
}) {
  const { currency, fromEur, toEur, formatMoneyFromEur } = useLocale();
  const toast = useToast();
  const [sessions, setSessions] = useState<any[]>([]);
  const [plans, setPlans] = useState<ChargingPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [formMode, setFormMode] = useState<"create" | "edit" | null>(null);
  const [editingSession, setEditingSession] = useState<any>(null);
  const editingIdRef = useRef<string | number | null>(null);
  const [editForm, setEditForm] = useState<FormFields>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
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

  const closeForm = () => {
    setFormMode(null);
    setEditingSession(null);
    setFormError(null);
    setSuggestion(null);
    editingIdRef.current = null;
  };

  const openCreate = () => {
    editingIdRef.current = null;
    setEditingSession(null);
    setSuggestion(null);
    setFormError(null);
    setEditForm(EMPTY_FORM);
    setFormMode("create");
  };

  const applySuggestion = (s: SuggestCost, session: any, overwriteCost: boolean) => {
    setSuggestion(s);
    const leaveUnpaid =
      s.reason === "within_allotment" ||
      s.reason === "mixed" ||
      s.suggested_paid_eur == null ||
      s.suggested_paid_eur <= 0;
    const fillPaid = overwriteCost && !leaveUnpaid;
    setEditForm((prev) => ({
      ...prev,
      charging_plan_id: s.plan_id || prev.charging_plan_id,
      provider_name: s.suggested_provider_name || prev.provider_name || session.provider_name || "",
      actual_cost_eur: overwriteCost
        ? (fillPaid ? String(fromEur(s.suggested_paid_eur) ?? "") : "")
        : prev.actual_cost_eur,
    }));
  };

  const openEditor = async (session: any) => {
    const sessionId = session.id;
    editingIdRef.current = sessionId;
    setEditingSession(session);
    setFormMode("edit");
    setFormError(null);
    setSuggestion(null);
    const hasPaid = session.actual_cost_eur != null;
    setEditForm({
      session_start: toDatetimeLocal(session.session_start),
      session_end: toDatetimeLocal(session.session_end),
      start_level: session.start_level != null ? String(session.start_level) : "",
      end_level: session.end_level != null ? String(session.end_level) : "",
      energy_kwh: session.energy_kwh != null ? String(session.energy_kwh) : "",
      actual_cost_eur: hasPaid ? String(fromEur(session.actual_cost_eur) ?? "") : "",
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
    const sessionId = editingSession.id;
    try {
      const formKwh = Number.parseFloat(editForm.energy_kwh);
      const s = await api.suggestChargingSessionCost(
        vehicleId,
        sessionId,
        planId,
        Number.isFinite(formKwh) ? formKwh : undefined
      );
      if (editingIdRef.current !== sessionId) return;
      applySuggestion(s, editingSession, editingSession.actual_cost_eur == null);
    } catch {
      if (editingIdRef.current !== sessionId) return;
      setSuggestion(null);
    }
  };

  const validateForm = (): string | null => {
    if (!editForm.session_start) return "Please pick a start time for the charge.";
    const start = new Date(editForm.session_start);
    if (Number.isNaN(start.getTime())) return "Please pick a valid start time.";
    if (editForm.session_end) {
      const end = new Date(editForm.session_end);
      if (Number.isNaN(end.getTime())) return "Please pick a valid end time, or leave it empty for an ongoing charge.";
      if (end.getTime() < start.getTime()) return "The end time must be after the start time.";
    }
    for (const key of ["start_level", "end_level"] as const) {
      const raw = editForm[key];
      if (raw === "") continue;
      const n = Number.parseFloat(raw);
      if (!Number.isFinite(n) || n < 0 || n > 100) return "State of charge must be between 0 and 100.";
    }
    for (const key of ["energy_kwh", "actual_cost_eur"] as const) {
      const raw = editForm[key];
      if (raw === "") continue;
      const n = Number.parseFloat(raw);
      if (!Number.isFinite(n) || n < 0) return "Energy and cost cannot be negative.";
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    const problem = validateForm();
    if (problem) {
      setFormError(problem);
      return;
    }
    const costDisplay = Number.parseFloat(editForm.actual_cost_eur);
    const costEur = Number.isNaN(costDisplay) ? null : (toEur(costDisplay, 2) ?? null);
    const body = {
      session_start: new Date(editForm.session_start).toISOString(),
      session_end: editForm.session_end ? new Date(editForm.session_end).toISOString() : null,
      start_level: parseOptionalNumber(editForm.start_level),
      end_level: parseOptionalNumber(editForm.end_level),
      energy_kwh: parseOptionalNumber(editForm.energy_kwh),
      actual_cost_eur: costEur,
      provider_name: editForm.provider_name || "",
    };
    try {
      if (formMode === "create") {
        await api.createChargingSession(vehicleId, {
          ...body,
          provider_name: editForm.provider_name || null,
        });
        toast.success("Charge added");
      } else if (editingSession) {
        await api.updateChargingSession(vehicleId, editingSession.id, {
          ...body,
          charging_plan_id: editForm.charging_plan_id || null,
        });
        toast.success("Charge updated");
      }
      closeForm();
      await fetchSessions();
      onChanged?.();
    } catch (err) {
      setFormError(humanError(err, "Could not save this charge. Please try again."));
    }
  };

  const endCharge = async (session: any) => {
    const body: Record<string, unknown> = { session_end: new Date().toISOString() };
    if (session.end_level != null) body.end_level = session.end_level;
    try {
      await api.updateChargingSession(vehicleId, session.id, body);
      toast.success("Charge ended");
      await fetchSessions();
      onChanged?.();
    } catch (err) {
      toast.error(humanError(err, "Could not end this charge. Please try again."));
    }
  };

  if (loading) return <div className="p-8 text-center text-iv-text-muted">Loading charging history...</div>;

  const selectedPlan = plans.find((p) => p.id === editForm.charging_plan_id);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={openCreate}
          className="inline-flex items-center gap-2 rounded-xl bg-iv-cyan px-4 py-2 text-sm font-medium text-white hover:bg-iv-cyan/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Add charge
        </button>
      </div>

      {sessions.length === 0 && (
        <p className="text-sm text-iv-text-muted">No charging sessions recorded yet.</p>
      )}

      {sessions.map((session) => {
        const hasPlanCost = session.plan_cost_eur != null;
        const hasPaid = session.actual_cost_eur != null && Number(session.actual_cost_eur) > 0;
        const displayCost = hasPlanCost
          ? session.plan_cost_eur
          : hasPaid
            ? session.actual_cost_eur
            : session.base_cost_eur;
        const costLabel = hasPlanCost
          ? (session.cost_label || "On plan")
          : hasPaid
            ? "Paid"
            : displayCost != null
              ? "Est. Base"
              : "";
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
                    {!session.session_end && (
                      <button
                        type="button"
                        onClick={() => endCharge(session)}
                        className="rounded-md border border-iv-border px-2 py-0.5 text-xs font-medium text-iv-cyan hover:bg-iv-surface transition-colors"
                      >
                        End charge
                      </button>
                    )}
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
                  <p className="text-sm text-iv-text-muted">{costLabel}</p>
                </div>
              </div>
            </div>
          </div>
        );
      })}

      {formMode && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl bg-iv-charcoal p-6 shadow-2xl border border-iv-border">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-bold text-iv-text">{formMode === "create" ? "Add Charge" : "Edit Charge"}</h3>
              <button type="button" onClick={closeForm} className="text-iv-text-muted hover:text-iv-text">
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="cs-start" className="block text-sm font-medium text-iv-text-muted mb-1">Start</label>
                  <input
                    id="cs-start"
                    type="datetime-local"
                    required
                    value={editForm.session_start}
                    onChange={(e) => setEditForm({ ...editForm, session_start: e.target.value })}
                    className="w-full rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-iv-text focus:border-iv-cyan focus:ring-1 focus:ring-iv-cyan outline-none transition-all"
                  />
                </div>
                <div>
                  <label htmlFor="cs-end" className="block text-sm font-medium text-iv-text-muted mb-1">End (empty = ongoing)</label>
                  <input
                    id="cs-end"
                    type="datetime-local"
                    value={editForm.session_end}
                    onChange={(e) => setEditForm({ ...editForm, session_end: e.target.value })}
                    className="w-full rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-iv-text focus:border-iv-cyan focus:ring-1 focus:ring-iv-cyan outline-none transition-all"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="cs-start-level" className="block text-sm font-medium text-iv-text-muted mb-1">Start SoC (%)</label>
                  <input
                    id="cs-start-level"
                    type="number"
                    min="0"
                    max="100"
                    step="0.1"
                    value={editForm.start_level}
                    onChange={(e) => setEditForm({ ...editForm, start_level: e.target.value })}
                    className="w-full rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-iv-text focus:border-iv-cyan focus:ring-1 focus:ring-iv-cyan outline-none transition-all"
                    placeholder="40"
                  />
                </div>
                <div>
                  <label htmlFor="cs-end-level" className="block text-sm font-medium text-iv-text-muted mb-1">End SoC (%)</label>
                  <input
                    id="cs-end-level"
                    type="number"
                    min="0"
                    max="100"
                    step="0.1"
                    value={editForm.end_level}
                    onChange={(e) => setEditForm({ ...editForm, end_level: e.target.value })}
                    className="w-full rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-iv-text focus:border-iv-cyan focus:ring-1 focus:ring-iv-cyan outline-none transition-all"
                    placeholder="80"
                  />
                </div>
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
                    min="0"
                    value={editForm.energy_kwh}
                    onChange={(e) => setEditForm({ ...editForm, energy_kwh: e.target.value })}
                    onBlur={() => {
                      if (editForm.charging_plan_id) onPlanChange(editForm.charging_plan_id);
                    }}
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
              {formMode === "edit" && (
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
                  {suggestionNote(suggestion, formatMoneyFromEur) && (
                    <p className="mt-1 text-xs text-iv-cyan">{suggestionNote(suggestion, formatMoneyFromEur)}</p>
                  )}
                  <Link href="/settings" className="mt-1 inline-block text-xs text-iv-cyan hover:underline">
                    Add plan in Settings
                  </Link>
                </div>
              )}
              {formMode === "edit" &&
                suggestion?.suggested_cost_eur != null &&
                (suggestion.reason === "within_allotment" || suggestion.reason === "mixed") && (
                <p className="text-sm text-iv-text">
                  On plan: <span className="font-semibold tabular-nums">{formatMoneyFromEur(suggestion.suggested_cost_eur)}</span>
                  <span className="text-iv-text-muted"> (counted from the subscription, not as paid at the charger)</span>
                </p>
              )}
              {formError && (
                <p className="text-sm text-red-400">{formError}</p>
              )}
              <div className="mt-6 flex justify-end gap-3">
                <button type="button" onClick={closeForm} className="px-4 py-2 rounded-xl text-sm font-medium text-iv-text bg-iv-surface hover:bg-iv-border transition-colors">
                  Cancel
                </button>
                <button type="submit" className="px-4 py-2 rounded-xl text-sm font-medium text-white bg-iv-cyan hover:bg-iv-cyan/90 transition-colors">
                  {formMode === "create" ? "Add Charge" : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
