"use client";

import { useEffect, useState } from "react";
import { CreditCard } from "lucide-react";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";
import { ChargingSessionsDashboard } from "@/components/statistics/ChargingSessionsDashboard";

interface SubscriptionUsage {
  plan_id: string;
  plan_name: string;
  plan_type: string;
  period_start: string | null;
  period_end: string | null;
  allotment_kwh: number | null;
  used_kwh: number;
  remaining_kwh: number | null;
  used_pct: number | null;
  period_fee_eur: number | null;
  allocated_eur: number;
  remaining_fee_eur: number | null;
  included_rate_eur: number | null;
  overage_kwh: number;
}

function formatChargingState(state: string | null | undefined): string {
  if (!state) return "—";
  if (state === "CONNECT_CABLE" || state === "DISCONNECTED") return "Disconnected";
  if (state === "READY_FOR_CHARGING") return "Ready to Charge";
  if (state === "CHARGING") return "Charging";
  if (state === "ERROR") return "Error";
  return state.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
}

function UsageRing({ usedPct }: { usedPct: number }) {
  const clamped = Math.min(100, Math.max(0, usedPct));
  return (
    <div
      className="relative h-24 w-24 shrink-0 rounded-full"
      style={{
        background: `conic-gradient(var(--iv-green) ${clamped * 3.6}deg, rgba(148,163,184,0.18) 0deg)`,
      }}
      aria-hidden
    >
      <div className="absolute inset-[7px] flex flex-col items-center justify-center rounded-full bg-iv-charcoal">
        <span className="text-lg font-semibold tabular-nums text-iv-text">{Math.round(clamped)}%</span>
        <span className="text-[10px] uppercase tracking-wide text-iv-muted">used</span>
      </div>
    </div>
  );
}

function SubscriptionUsageCard({
  vehicleId,
  refreshToken,
}: {
  vehicleId: string;
  refreshToken: number;
}) {
  const { formatMoneyFromEur } = useLocale();
  const [plans, setPlans] = useState<SubscriptionUsage[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getChargingPlanUsage(vehicleId)
      .then((data) => {
        if (!cancelled) setPlans(data?.plans ?? []);
      })
      .catch(() => {
        if (!cancelled) setPlans([]);
      });
    return () => {
      cancelled = true;
    };
  }, [vehicleId, refreshToken]);

  if (plans == null || plans.length === 0) return null;

  return (
    <div className="glass flex-1 rounded-xl border border-iv-border p-5 lg:max-w-sm">
      <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-iv-muted">
        <CreditCard className="h-4 w-4 text-iv-cyan" />
        Subscription
      </h3>
      <div className="space-y-5">
        {plans.map((plan) => (
          <div key={plan.plan_id} className="flex items-center gap-4">
            {plan.allotment_kwh != null ? (
              <UsageRing usedPct={plan.used_pct ?? 0} />
            ) : (
              <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-full border border-iv-border text-iv-cyan">
                <CreditCard className="h-7 w-7" />
              </div>
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium text-iv-text">{plan.plan_name}</p>
              {plan.allotment_kwh != null ? (
                <>
                  <p className="mt-1 text-sm text-iv-text">
                    <span className="tabular-nums font-semibold">
                      {plan.remaining_kwh != null ? plan.remaining_kwh.toFixed(2) : "—"} kWh
                    </span>
                    <span className="text-iv-muted"> left of {plan.allotment_kwh} kWh</span>
                  </p>
                  <p className="mt-1 text-xs text-iv-muted">
                    {plan.used_kwh.toFixed(2)} kWh used
                    {plan.remaining_fee_eur != null && plan.period_fee_eur != null
                      ? ` · ${formatMoneyFromEur(plan.remaining_fee_eur)} of ${formatMoneyFromEur(plan.period_fee_eur)} left`
                      : ""}
                  </p>
                </>
              ) : (
                <p className="mt-1 text-sm text-iv-muted">
                  {plan.used_kwh.toFixed(2)} kWh this period
                  {plan.period_fee_eur != null ? ` · ${formatMoneyFromEur(plan.period_fee_eur)} period fee` : ""}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function VehicleChargingPanel({
  vehicleId,
  chargingState,
  chargingPowerKw,
  remainingChargeTimeMin,
  targetSoc,
}: {
  vehicleId: string;
  chargingState?: string | null;
  chargingPowerKw?: number | null;
  remainingChargeTimeMin?: number | null;
  targetSoc?: number | null;
}) {
  const [refreshToken, setRefreshToken] = useState(0);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-stretch">
        <SubscriptionUsageCard vehicleId={vehicleId} refreshToken={refreshToken} />
        {chargingState ? (
          <div className="glass flex-1 rounded-xl p-5">
            <h3 className="mb-3 text-sm font-medium text-iv-muted">Current Charging Status</h3>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <p className="text-xs text-iv-muted">State</p>
                <p className={`text-sm font-semibold ${chargingState === "CHARGING" ? "text-iv-green" : "text-iv-text"}`}>
                  {formatChargingState(chargingState)}
                </p>
              </div>
              <div>
                <p className="text-xs text-iv-muted">Power</p>
                <p className="text-sm font-semibold text-iv-text">
                  {chargingPowerKw != null ? `${chargingPowerKw} kW` : "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-iv-muted">Time Remaining</p>
                <p className="text-sm font-semibold text-iv-text">
                  {remainingChargeTimeMin != null ? `${remainingChargeTimeMin} min` : "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-iv-muted">Target SoC</p>
                <p className="text-sm font-semibold text-iv-cyan">
                  {targetSoc != null ? `${targetSoc}%` : "—"}
                </p>
              </div>
            </div>
          </div>
        ) : null}
      </div>
      <ChargingSessionsDashboard
        vehicleId={vehicleId}
        onChanged={() => setRefreshToken((n) => n + 1)}
      />
    </div>
  );
}
