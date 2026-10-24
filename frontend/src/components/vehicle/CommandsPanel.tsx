"use client";

import { useState, type ElementType, type ReactNode } from "react";
import {
  CheckCircle2,
  Loader2,
  Lock,
  LockOpen,
  Power,
  RotateCcw,
  Volume2,
  XCircle,
  Zap,
  ZapOff,
} from "lucide-react";

import { PasswordInput } from "@/components/password-input";
import { cn } from "@/lib/cn";

import { ClimateDial } from "./ClimateDial";

type CmdResult = { status: "success" | "error"; message: string };

export type CommandsPanelProps = {
  climateTempC: number;
  onClimateTempC: (c: number) => void;
  usesFahrenheit?: boolean;
  climateRunning: boolean;
  charging: boolean | null;
  locked: boolean | null;
  hasLogin: boolean;
  hasApiKey: boolean;
  cmdLoading: string | null;
  cmdResult: CmdResult | null;
  onCommand: (command: string, body?: object) => void;
  onRetry: () => void;
};

/** Match ClimateDial’s display so Restart label numbers agree with the dial. */
function toF(c: number) {
  return Math.round(((c * 9) / 5 + 32) * 10) / 10;
}

function formatTemp(c: number, usesFahrenheit: boolean) {
  if (usesFahrenheit) return `${toF(c)}`;
  return c.toFixed(1).replace(/\.0$/, "");
}

function ActionRow({
  icon: Icon,
  label,
  hint,
  actionLabel,
  disabled,
  loading,
  danger,
  onClick,
  children,
  actionAriaLabel,
}: {
  icon: ElementType;
  label: string;
  hint?: string;
  actionLabel: string;
  disabled?: boolean;
  loading?: boolean;
  danger?: boolean;
  onClick: () => void;
  /** Optional control placed between the text block and the action button. */
  children?: ReactNode;
  actionAriaLabel?: string;
}) {
  return (
    <div className="glass flex flex-wrap items-center gap-3 rounded-2xl p-4">
      <div
        className={cn(
          "flex h-10 w-10 shrink-0 items-center justify-center rounded-full",
          danger ? "bg-iv-warning/10 text-iv-warning" : "bg-iv-green/10 text-iv-green"
        )}
        aria-hidden="true"
      >
        <Icon size={18} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-iv-text">{label}</p>
        {hint ? <p className="text-xs text-iv-muted">{hint}</p> : null}
      </div>
      {children}
      <button
        type="button"
        onClick={onClick}
        disabled={disabled || loading}
        aria-label={actionAriaLabel}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40",
          danger
            ? "border border-iv-warning/30 bg-iv-warning/10 text-iv-warning hover:bg-iv-warning/20"
            : "bg-iv-text text-iv-black hover:opacity-90"
        )}
      >
        {loading ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : null}
        {actionLabel}
      </button>
    </div>
  );
}

export function CommandsPanel({
  climateTempC,
  onClimateTempC,
  usesFahrenheit = false,
  climateRunning,
  charging,
  locked,
  hasLogin,
  hasApiKey,
  cmdLoading,
  cmdResult,
  onCommand,
  onRetry,
}: CommandsPanelProps): JSX.Element {
  const [spin, setSpin] = useState("");

  const canAnyCommand = hasLogin || hasApiKey;
  const canLoginActions = hasLogin;
  const noSourceHint = "Connect MyŠkoda Login or add an API key first.";

  const tempDisplay = formatTemp(climateTempC, usesFahrenheit);
  const restartLabel = `Restart at ${tempDisplay}°${usesFahrenheit ? "F" : "C"}`;

  const chargingCommand = charging ? "charging/stop" : "charging/start";

  return (
    <div className="grid gap-6 lg:grid-cols-2 lg:items-start">
      {/* ── Climate hero + result toast ─────────────────────────── */}
      <div className="space-y-3">
        <ClimateDial
          tempC={climateTempC}
          onChangeC={onClimateTempC}
          usesFahrenheit={usesFahrenheit}
          disabled={!canAnyCommand}
          running={climateRunning}
          startLabel={climateRunning ? restartLabel : undefined}
          loadingStart={cmdLoading === "climatization/start"}
          loadingStop={cmdLoading === "climatization/stop"}
          onStart={() =>
            onCommand("climatization/start", { target_temperature: climateTempC })
          }
          onStop={() => onCommand("climatization/stop")}
        />

        {!canAnyCommand ? (
          <p className="text-center text-xs text-iv-muted">{noSourceHint}</p>
        ) : null}

        {cmdResult ? (
          <div
            role="status"
            aria-live="polite"
            className={cn(
              "flex items-start gap-2 rounded-xl px-4 py-3 text-sm",
              cmdResult.status === "success"
                ? "bg-iv-green/15 text-iv-green"
                : "bg-iv-danger/15 text-iv-danger"
            )}
          >
            {cmdResult.status === "success" ? (
              <CheckCircle2 size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
            ) : (
              <XCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
            )}
            <div className="min-w-0 flex-1">
              <p>{cmdResult.message}</p>
              {cmdResult.status === "error" ? (
                <button
                  type="button"
                  onClick={onRetry}
                  className="mt-1.5 inline-flex items-center gap-1 rounded-md text-xs font-semibold underline underline-offset-2 hover:opacity-80"
                >
                  <RotateCcw size={12} aria-hidden="true" />
                  Retry
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>

      {/* ── Action rows ─────────────────────────────────────────── */}
      <div className="space-y-3">
        <ActionRow
          icon={charging ? ZapOff : Zap}
          label="Charging"
          hint={
            !canAnyCommand
              ? noSourceHint
              : charging
                ? "Charging is active."
                : charging === false
                  ? "Start or stop charging remotely."
                  : "Charging status unknown."
          }
          actionLabel={charging ? "Stop" : "Start"}
          actionAriaLabel={charging ? "Stop charging" : "Start charging"}
          disabled={!canAnyCommand}
          loading={cmdLoading === chargingCommand}
          onClick={() => onCommand(chargingCommand)}
        />

        <ActionRow
          icon={locked ? Lock : LockOpen}
          label="Lock"
          hint={
            !canLoginActions
              ? "Connect MyŠkoda Login to lock."
              : locked === true
                ? "The vehicle is already locked."
                : "Lock the vehicle remotely."
          }
          actionLabel="Lock"
          disabled={!canLoginActions || locked === true}
          loading={cmdLoading === "lock"}
          onClick={() => onCommand("lock")}
        />

        <ActionRow
          icon={LockOpen}
          label="Unlock"
          hint={
            canLoginActions
              ? "Needs your vehicle S-PIN."
              : "Connect MyŠkoda Login to unlock."
          }
          actionLabel="Unlock"
          danger
          disabled={!canLoginActions || spin.trim().length === 0}
          loading={cmdLoading === "unlock"}
          onClick={() => onCommand("unlock", { spin: spin.trim() })}
        >
          <PasswordInput
            value={spin}
            onChange={(e) => setSpin(e.target.value)}
            placeholder="S-PIN"
            aria-label="Vehicle S-PIN"
            autoComplete="off"
            disabled={!canLoginActions}
            wrapperClassName="w-28 shrink-0"
            className="w-full rounded-xl border border-iv-border bg-iv-surface px-3 py-2 text-center text-sm text-iv-text placeholder:text-iv-muted focus:border-iv-cyan focus:outline-none focus:ring-1 focus:ring-iv-cyan disabled:cursor-not-allowed disabled:opacity-40"
          />
        </ActionRow>

        <ActionRow
          icon={Volume2}
          label="Find"
          hint="Honk and flash is not available on this connection."
          actionLabel="Honk & Flash"
          disabled
          onClick={() => onCommand("honk-flash")}
        />

        <ActionRow
          icon={Power}
          label="Wake up"
          hint={
            canLoginActions
              ? "Wake the car so it accepts remote commands."
              : "Connect MyŠkoda Login to wake the car."
          }
          actionLabel="Wake"
          disabled={!canLoginActions}
          loading={cmdLoading === "wake"}
          onClick={() => onCommand("wake")}
        />
      </div>
    </div>
  );
}
