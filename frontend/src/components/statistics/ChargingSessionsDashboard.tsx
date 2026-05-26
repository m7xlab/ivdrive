"use client";

import { useEffect, useState } from "react";
import { format, parseISO } from "date-fns";
import { Plug, Zap, Banknote, Edit, X } from "lucide-react";
import { api } from "@/lib/api";

export function ChargingSessionsDashboard({ vehicleId }: { vehicleId: string }) {
  const [sessions, setSessions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingSession, setEditingSession] = useState<any>(null);
  const [editForm, setEditForm] = useState({ actual_cost_eur: "", energy_kwh: "", provider_name: "" });

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

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingSession) return;
    
    try {
      await api.updateChargingSession(vehicleId, editingSession.id, {
        actual_cost_eur: parseFloat(editForm.actual_cost_eur) || 0,
        energy_kwh: parseFloat(editForm.energy_kwh) || 0,
        provider_name: editForm.provider_name || ""
      });
      setEditingSession(null);
      fetchSessions();
    } catch (err) {
      console.error("Update failed", err);
    }
  };

  if (loading) return <div className="p-8 text-center text-iv-text-muted">Loading charging history...</div>;

  return (
    <div className="space-y-4">
      {sessions.map((session) => (
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
                    type="button"onClick={() => {
                      setEditingSession(session);
                      setEditForm({
                        actual_cost_eur: session.actual_cost_eur?.toString() || "",
                        energy_kwh: session.energy_kwh?.toString() || "",
                        provider_name: session.provider_name || ""
                      });
                    }}
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
                  {session.energy_kwh ? `${session.energy_kwh} kWh` : "--"}
                </p>
                <p className="text-sm text-iv-text-muted">
                  {session.start_level}% &rarr; {session.end_level}%
                </p>
              </div>
              <div className="hidden sm:block">
                <p className="font-semibold text-iv-text flex items-center justify-end gap-1">
                  <Banknote className="h-4 w-4 text-emerald-500" />
                  {session.actual_cost_eur || session.base_cost_eur || "--"}
                </p>
                <p className="text-sm text-iv-text-muted">
                  {session.actual_cost_eur ? "Paid" : "Est. Base"}
                </p>
              </div>
            </div>
          </div>
        </div>
      ))}

      {/* Edit Modal */}
      {editingSession && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl bg-iv-charcoal p-6 shadow-2xl border border-iv-border">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-bold text-iv-text">Edit Receipt Data</h3>
              <button type="button"onClick={() => setEditingSession(null)} className="text-iv-text-muted hover:text-iv-text">
                <X className="h-5 w-5" />
              </button>
            </div>
            
            <form onSubmit={handleEditSubmit} className="space-y-4">
              <div>
                <label htmlFor="cs-provider-name" className="block text-sm font-medium text-iv-text-muted mb-1">Provider Name</label>
                <input 
                  id="cs-provider-name"
                  type="text" 
                  value={editForm.provider_name}
                  onChange={e => setEditForm({...editForm, provider_name: e.target.value})}
                  className="w-full rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-iv-text focus:border-iv-cyan focus:ring-1 focus:ring-iv-cyan outline-none transition-all"
                  placeholder="e.g. IgnitisON"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="cs-energy-kwh" className="block text-sm font-medium text-iv-text-muted mb-1">Energy Added (kWh)</label>
                  <input 
                    id="cs-energy-kwh"
                    type="number" step="0.01"
                    value={editForm.energy_kwh}
                    onChange={e => setEditForm({...editForm, energy_kwh: e.target.value})}
                    className="w-full rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-iv-text focus:border-iv-cyan focus:ring-1 focus:ring-iv-cyan outline-none transition-all"
                    placeholder="29.83"
                  />
                </div>
                <div>
                  <label htmlFor="cs-cost-eur" className="block text-sm font-medium text-iv-text-muted mb-1">Total Paid (€)</label>
                  <input 
                    id="cs-cost-eur"
                    type="number" step="0.01"
                    value={editForm.actual_cost_eur}
                    onChange={e => setEditForm({...editForm, actual_cost_eur: e.target.value})}
                    className="w-full rounded-lg bg-iv-surface border border-iv-border px-4 py-2.5 text-iv-text focus:border-iv-cyan focus:ring-1 focus:ring-iv-cyan outline-none transition-all"
                    placeholder="9.55"
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
