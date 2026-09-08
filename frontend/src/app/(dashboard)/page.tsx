"use client";



import { useCallback, useEffect, useState } from "react";

import { Plus, Car, X, Loader2, AlertCircle, Timer } from "lucide-react";

import { api } from "@/lib/api";

import { useLocale } from "@/lib/locale";

import { useAuth } from "@/lib/auth-context";

import { VehicleCard, CardSkeleton } from "@/components/vehicle-card";

import {
  useVehicles,
  useVehicleStatus,
  useDeleteVehicle,
  type Vehicle,
  type VehicleStatus,
} from "@/lib/hooks/use-vehicles";

import { AuthReauthBanner, AuthMethodPill, ConnectorErrorPill } from "@/components/auth-banner";

/** Wrapper component to isolate per-vehicle data fetching. */
function VehicleRow({ vehicle, onDeleteRequest, onRefetch }: { vehicle: Vehicle, onDeleteRequest: (id: string) => void, onRefetch: () => void }) {
  const { data: status, isLoading } = useVehicleStatus(vehicle.id);
  
  return (
    <div className="space-y-3">
      <AuthReauthBanner vehicle={vehicle} />
      <VehicleCard
        vehicleId={vehicle.id}
        displayName={vehicle.display_name ?? undefined}
        manufacturer={vehicle.manufacturer ?? undefined}
        model={vehicle.model ?? undefined}
        modelYear={vehicle.model_year ?? null}
        imageUrl={vehicle.image_url}
        connectorStatus={vehicle.connector_status}
        status={status ?? null}
        loading={isLoading}
        onDelete={onDeleteRequest}
        onAfterRefresh={onRefetch}
        authPill={<AuthMethodPill vehicle={vehicle} />}
        errorPill={<ConnectorErrorPill vehicle={vehicle} />}
      />
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [showAddModal, setShowAddModal] = useState(false);
  const [deleteModal, setDeleteModal] = useState<{ id: string; name: string } | null>(null);

  // ── Data fetching via React Query ────────────────────────────────────────
  const vehiclesQuery = useVehicles();
  const vehicles: Vehicle[] = vehiclesQuery.data ?? [];
  const loadingVehicles = vehiclesQuery.isLoading;

  const handleVehicleAdded = () => setShowAddModal(false);

  const handleDeleteRequest = (id: string) => {
    const v = vehicles.find((vv) => vv.id === id);
    setDeleteModal({
      id,
      name: v?.display_name || (v?.manufacturer ? `${v.manufacturer} ${v.model}` : "this vehicle"),
    });
  };

  const deleteVehicle = useDeleteVehicle();
  const handleDeleteConfirm = async () => {
    if (!deleteModal) return;
    await deleteVehicle.mutateAsync(deleteModal.id);
    setDeleteModal(null);
  };




  return (

    <div className="mx-auto max-w-7xl">

      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">

        <div>

          <h1 className="text-2xl font-bold text-iv-text sm:text-3xl">

            Welcome back,{" "}

            <span className="gradient-text">

              {user?.display_name || "Driver"}

            </span>

          </h1>

          <p className="mt-1 text-iv-muted">Your Vehicles</p>

        </div>

        <button type="button"

          onClick={() => setShowAddModal(true)}

          className="inline-flex items-center gap-2 rounded-xl bg-iv-green/15 px-4 py-2.5 text-sm font-medium text-iv-green border border-iv-green/20 transition-all hover:bg-iv-green/25 hover:glow-green"

        >

          <Plus size={18} />

          Add Vehicle

        </button>

      </div>



      {loadingVehicles ? (

        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">

          {[1, 2, 3].map((i) => (

            <CardSkeleton key={i} />

          ))}

        </div>

      ) : vehicles.length === 0 ? (

        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-iv-border bg-iv-surface/30 py-20">

          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-iv-green/10">

            <Car size={28} className="text-iv-green" />

          </div>

          <h2 className="text-lg font-semibold text-iv-text">

            No vehicles yet

          </h2>

          <p className="mt-1 text-sm text-iv-muted">

            Add your first vehicle to start monitoring

          </p>

          <button type="button"

            onClick={() => setShowAddModal(true)}

            className="mt-6 inline-flex items-center gap-2 rounded-xl bg-iv-green/15 px-5 py-2.5 text-sm font-medium text-iv-green border border-iv-green/20 transition-all hover:bg-iv-green/25 hover:glow-green"

          >

            <Plus size={18} />

            Add your first vehicle

          </button>

        </div>

      ) : (

        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {vehicles.map((v) => (
            <VehicleRow 
              key={v.id} 
              vehicle={v} 
              onDeleteRequest={handleDeleteRequest} 
              onRefetch={() => vehiclesQuery.refetch()} 
            />
          ))}
        </div>

      )}



      {showAddModal && (

        <AddVehicleModal

          onClose={() => setShowAddModal(false)}

          onSuccess={handleVehicleAdded}

        />

      )}



      {deleteModal && (

        <ConfirmDeleteModal

          name={deleteModal.name}

          onConfirm={handleDeleteConfirm}

          onCancel={() => setDeleteModal(null)}

        />

      )}

    </div>

  );

}



function ConfirmDeleteModal({

  name,

  onConfirm,

  onCancel,

}: {

  name: string;

  onConfirm: () => Promise<void>;

  onCancel: () => void;

}) {

  const [loading, setLoading] = useState(false);



  const handleConfirm = async () => {

    setLoading(true);

    try {

      await onConfirm();

    } finally {

      setLoading(false);

    }

  };



  return (

    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">

      <div
        role="button"
        tabIndex={0}
        aria-label="Close dialog"
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onCancel(); } }}
      />

      <div className="glass relative w-full max-w-sm rounded-2xl p-6">

        <h2 className="text-lg font-semibold text-iv-text mb-2">Delete Vehicle</h2>

        <p className="text-sm text-iv-muted mb-6">

          Are you sure you want to delete <strong className="text-iv-text">{name}</strong>?

          All collected data will be permanently removed.

        </p>

        <div className="flex gap-3">

          <button type="button"

            onClick={onCancel}

            className="flex-1 rounded-xl border border-iv-border px-4 py-2.5 text-sm font-medium text-iv-muted transition-colors hover:bg-iv-surface hover:text-iv-text"

          >

            Cancel

          </button>

          <button type="button"

            onClick={handleConfirm}

            disabled={loading}

            className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-iv-danger px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-iv-danger/90 disabled:opacity-50"

          >

            {loading ? <Loader2 size={16} className="animate-spin" /> : null}

            Delete

          </button>

        </div>

      </div>

    </div>

  );

}



function AddVehicleModal({

  onClose,

  onSuccess,

}: {

  onClose: () => void;

  onSuccess: () => void;

}) {

  const { distanceLabel, displayToKm } = useLocale();

  const [vin, setVin] = useState("");

  const [displayName, setDisplayName] = useState("");

  const [skodaUsername, setSkodaUsername] = useState("");

  const [skodaPassword, setSkodaPassword] = useState("");

  const [skodaSpin, setSkodaSpin] = useState("");

  const [wltpRangeKm, setWltpRangeKm] = useState("");

  const [activeInterval, setActiveInterval] = useState(300);

  const [parkedInterval, setParkedInterval] = useState(1800);

  const [submitting, setSubmitting] = useState(false);

  const [error, setError] = useState<string | null>(null);



  const handleSubmit = async (e: React.FormEvent) => {

    e.preventDefault();

    setError(null);

    setSubmitting(true);



    try {

      await api.addVehicle({

        vin,

        display_name: displayName || undefined,

        skoda_username: skodaUsername,

        skoda_password: skodaPassword,

        skoda_spin: skodaSpin || undefined,

        active_interval_seconds: activeInterval,

        parked_interval_seconds: parkedInterval,

        wltp_range_km: wltpRangeKm ? displayToKm(parseFloat(wltpRangeKm)) : null,

      });

      onSuccess();

    } catch (err) {

      setError(err instanceof Error ? err.message : "Failed to add vehicle");

    } finally {

      setSubmitting(false);

    }

  };



  const intervalLabel = (s: number) => {

    if (s < 60) return `${s}s`;

    const m = Math.floor(s / 60);

    return m < 60 ? `${m} min` : `${Math.floor(m / 60)}h ${m % 60}m`;

  };



  return (

    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">

      <div


        role="button"


        tabIndex={0}


        aria-label="Close dialog"


        className="absolute inset-0 bg-black/60 backdrop-blur-sm"


        onClick={onClose}


        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClose(); } }}


      />

      <div className="glass relative w-full max-w-md rounded-2xl p-6 glow-green">

        <div className="mb-6 flex items-center justify-between">

          <h2 className="text-lg font-semibold text-iv-text">Add Vehicle</h2>

          <button type="button"

            onClick={onClose}

            className="rounded-lg p-1.5 text-iv-muted transition-colors hover:bg-iv-surface hover:text-iv-text"

          >

            <X size={18} />

          </button>

        </div>



        {error && (

          <div className="mb-4 flex items-center gap-2 rounded-lg bg-iv-danger/10 border border-iv-danger/20 px-3 py-2 text-sm text-iv-danger">

            <AlertCircle size={16} className="flex-shrink-0" />

            {error}

          </div>

        )}



        <form onSubmit={handleSubmit} className="space-y-4">

          <FormField

            label="VIN"

            required

            value={vin}

            onChange={setVin}

            placeholder="Vehicle Identification Number"

          />

          <FormField

            label="Display Name"

            value={displayName}

            onChange={setDisplayName}

            placeholder="e.g. My Enyaq"

          />

          <FormField

            label="Skoda Username"

            required

            value={skodaUsername}

            onChange={setSkodaUsername}

            placeholder="Skoda Connect email"

          />

          <FormField

            label="Skoda Password"

            required

            type="password"

            value={skodaPassword}

            onChange={setSkodaPassword}

            placeholder="Skoda Connect password"

          />

          <FormField

            label="Skoda S-PIN"

            value={skodaSpin}

            onChange={setSkodaSpin}

            placeholder="Optional 4-digit S-PIN"

          />

          <FormField

            label={`WLTP Range (${distanceLabel})`}

            type="number"

            value={wltpRangeKm}

            onChange={setWltpRangeKm}

            placeholder="e.g. 510 — used for Efficiency % chart"

          />



          <div>

            <label className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-iv-text">

              <Timer size={14} className="text-iv-muted" />

              Active Telemetry Rate

              <span className="ml-auto text-xs text-iv-cyan font-mono">{intervalLabel(activeInterval)}</span>

            </label>

            <input

              type="range"

              min={60}

              max={1800}

              step={60}

              value={activeInterval}

              onChange={(e) => setActiveInterval(Number(e.target.value))}

              className="w-full accent-iv-green"

            />

            <div className="flex justify-between text-xs text-iv-muted mt-1">

              <span>1 min</span>

              <span>30 min</span>

            </div>

          </div>

          <div>

            <label className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-iv-text">

              <Timer size={14} className="text-iv-muted" />

              Parked Check Rate

              <span className="ml-auto text-xs text-iv-cyan font-mono">{intervalLabel(parkedInterval)}</span>

            </label>

            <input

              type="range"

              min={300}

              max={7200}

              step={300}

              value={parkedInterval}

              onChange={(e) => setParkedInterval(Number(e.target.value))}

              className="w-full accent-iv-cyan"

            />

            <div className="flex justify-between text-xs text-iv-muted mt-1">

              <span>5 min</span>

              <span>2 hours</span>

            </div>

          </div>



          <div className="flex gap-3 pt-2">

            <button

              type="button"

              onClick={onClose}

              className="flex-1 rounded-xl border border-iv-border px-4 py-2.5 text-sm font-medium text-iv-muted transition-colors hover:bg-iv-surface hover:text-iv-text"

            >

              Cancel

            </button>

            <button

              type="submit"

              disabled={submitting || !vin || !skodaUsername || !skodaPassword}

              className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-iv-green px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-iv-green/90 disabled:opacity-40 disabled:cursor-not-allowed"

            >

              {submitting ? (

                <>

                  <Loader2 size={16} className="animate-spin" />

                  Adding...

                </>

              ) : (

                "Add Vehicle"

              )}

            </button>

          </div>

        </form>

      </div>

    </div>

  );

}



function FormField({

  label,

  required,

  type = "text",

  value,

  onChange,

  placeholder,

}: {

  label: string;

  required?: boolean;

  type?: string;

  value: string;

  onChange: (v: string) => void;

  placeholder?: string;

}) {

  return (

    <div>

      <label className="mb-1.5 block text-sm font-medium text-iv-text">

        {label}

        {required && <span className="ml-0.5 text-iv-green">*</span>}

      </label>

      <input

        type={type}

        required={required}

        value={value}

        onChange={(e) => onChange(e.target.value)}

        placeholder={placeholder}

        className="w-full rounded-lg border border-iv-border bg-iv-surface px-3 py-2.5 text-sm text-iv-text placeholder:text-iv-muted/50 outline-none transition-colors focus:border-iv-green/50 focus:ring-1 focus:ring-iv-green/20"

      />

    </div>

  );

}
