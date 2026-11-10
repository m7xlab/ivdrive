"use client";

import { useState } from "react";
import { format, parseISO } from "date-fns";
import { Loader2, X } from "lucide-react";

import { api } from "@/lib/api";

export interface EditableTrip {
  trip_id: number;
  start_time: string;
  end_time: string;
  distance_km: number;
  kwh_used?: number | null;
}

// --- Data-quality badge --------------------------------------------------------------------

const QUALITY: Record<string, { label: string; tip: string; cls: string }> = {
  estimated_start: {
    label: "Est. start",
    tip: "The departure fell between two polls, so the start time is approximate.",
    cls: "bg-amber-500/10 text-amber-500",
  },
  estimated_end: {
    label: "Est. end",
    tip: "The distance was completed from a later odometer reading.",
    cls: "bg-amber-500/10 text-amber-500",
  },
  estimated_times: {
    label: "Est. times",
    tip: "MyŠkoda had no usable times for this drive. The end is when the odometer first showed the new value and the start is a typical drive time earlier, so both can be off by several minutes. Battery and energy come from your own records.",
    cls: "bg-amber-500/10 text-amber-500",
  },
  reconstructed: {
    label: "Rebuilt",
    tip: "Rebuilt from odometer readings. There is no route for this trip.",
    cls: "bg-amber-500/10 text-amber-500",
  },
  skoda_history: {
    label: "MyŠkoda",
    tip: "Taken from MyŠkoda's journey history.",
    cls: "bg-iv-cyan/10 text-iv-cyan",
  },
  manually_corrected: {
    label: "Edited",
    tip: "You corrected this trip. Automatic syncs leave it as it is.",
    cls: "bg-iv-cyan/10 text-iv-cyan",
  },
};

export function TripQualityBadge({ quality, edited }: { quality?: string | null; edited?: boolean }) {
  const key = edited ? "manually_corrected" : quality ?? "";
  const q = QUALITY[key];
  if (!q) return null; // measured: nothing to explain
  return (
    <span title={q.tip} className={`ml-2 px-1.5 py-0.5 rounded text-[9px] font-semibold align-middle ${q.cls}`}>
      {q.label}
    </span>
  );
}

// --- Dialog shell --------------------------------------------------------------------------

function Shell({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <div className="glass rounded-2xl p-5 w-full max-w-md bg-iv-surface" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-iv-text">{title}</h3>
          <button type="button" aria-label="Close" onClick={onClose} className="text-iv-muted hover:text-iv-text">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// --- Edit ----------------------------------------------------------------------------------

const toLocalInput = (iso: string) => format(parseISO(iso), "yyyy-MM-dd'T'HH:mm");

export function TripEditDialog({
  vehicleId,
  trip,
  onClose,
  onDone,
}: {
  vehicleId: string;
  trip: EditableTrip;
  onClose: () => void;
  onDone: () => void;
}) {
  const initial = {
    start: toLocalInput(trip.start_time),
    end: toLocalInput(trip.end_time),
    km: String(trip.distance_km ?? ""),
    kwh: trip.kwh_used != null ? String(Math.round(trip.kwh_used * 100) / 100) : "",
  };
  const [start, setStart] = useState(initial.start);
  const [end, setEnd] = useState(initial.end);
  const [km, setKm] = useState(initial.km);
  const [kwh, setKwh] = useState(initial.kwh);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    // Send only what changed, so untouched times keep their seconds.
    const body: { start_date?: string; end_date?: string; distance_km?: number; kwh_consumed?: number } = {};
    if (start !== initial.start) body.start_date = new Date(start).toISOString();
    if (end !== initial.end) body.end_date = new Date(end).toISOString();
    if (km !== initial.km && km.trim() !== "") body.distance_km = Number(km);
    if (kwh !== initial.kwh && kwh.trim() !== "") body.kwh_consumed = Number(kwh);
    if (Object.values(body).some((v) => typeof v === "number" && !Number.isFinite(v))) {
      setError("Enter numbers for distance and energy.");
      return;
    }
    if (Object.keys(body).length === 0) {
      onClose();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.editTrip(vehicleId, trip.trip_id, body);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the trip.");
      setBusy(false);
    }
  };

  const field = "w-full rounded-lg bg-iv-surface/60 border border-iv-border/60 px-3 py-2 text-sm text-iv-text";
  return (
    <Shell title="Edit trip" onClose={onClose}>
      <div className="space-y-3">
        <label className="block text-[11px] text-iv-muted">
          Start
          <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className={field} />
        </label>
        <label className="block text-[11px] text-iv-muted">
          End
          <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} className={field} />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-[11px] text-iv-muted">
            Distance (km)
            <input inputMode="decimal" value={km} onChange={(e) => setKm(e.target.value)} className={field} />
          </label>
          <label className="block text-[11px] text-iv-muted">
            Energy used (kWh)
            <input inputMode="decimal" value={kwh} onChange={(e) => setKwh(e.target.value)} className={field} />
          </label>
        </div>
        <p className="text-[10px] text-iv-muted">
          The original values are kept in the trip&apos;s history. Automatic syncs will not change an edited trip.
        </p>
        {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="px-3 py-2 rounded-lg text-xs text-iv-muted hover:text-iv-text">
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            disabled={busy}
            className="px-3 py-2 rounded-lg text-xs font-semibold bg-iv-cyan/20 text-iv-cyan hover:bg-iv-cyan/30 disabled:opacity-50 flex items-center gap-2"
          >
            {busy && <Loader2 size={12} className="animate-spin" />} Save
          </button>
        </div>
      </div>
    </Shell>
  );
}

// --- Delete --------------------------------------------------------------------------------

export function TripDeleteDialog({
  vehicleId,
  trip,
  onClose,
  onDone,
}: {
  vehicleId: string;
  trip: EditableTrip;
  onClose: () => void;
  onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.deleteTrip(vehicleId, trip.trip_id);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete the trip.");
      setBusy(false);
    }
  };

  return (
    <Shell title="Delete trip?" onClose={onClose}>
      <p className="text-xs text-iv-muted mb-4">
        {format(parseISO(trip.start_time), "MMM d, HH:mm")} · {trip.distance_km} km. The trip is removed from your
        history and statistics, and the MyŠkoda sync will not bring it back. This cannot be undone.
      </p>
      {error && <p role="alert" className="text-xs text-red-400 mb-3">{error}</p>}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onClose} className="px-3 py-2 rounded-lg text-xs text-iv-muted hover:text-iv-text">
          Cancel
        </button>
        <button
          type="button"
          onClick={remove}
          disabled={busy}
          className="px-3 py-2 rounded-lg text-xs font-semibold bg-red-500/20 text-red-400 hover:bg-red-500/30 disabled:opacity-50 flex items-center gap-2"
        >
          {busy && <Loader2 size={12} className="animate-spin" />} Delete
        </button>
      </div>
    </Shell>
  );
}
