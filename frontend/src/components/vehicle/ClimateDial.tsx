"use client";

import { Loader2, Minus, Plus, Power, Wind } from "lucide-react";

const MIN_DEFAULT = 16;
const MAX_DEFAULT = 30;
const STEP = 0.5;

/** 300° ring with a 60° gap at the bottom (defrost mark sits in the gap). */
const ARC_DEG = 300;
const ARC = ARC_DEG / 360;
/** Rotate so the gap is centered at the bottom (6 o'clock). */
const ROTATE = 90 + (360 - ARC_DEG) / 2;

function toF(c: number) {
  return Math.round(((c * 9) / 5 + 32) * 10) / 10;
}

function formatTemp(c: number, usesFahrenheit: boolean) {
  if (usesFahrenheit) return `${toF(c)}`;
  return c.toFixed(1).replace(/\.0$/, "");
}

export type ClimateDialProps = {
  tempC: number;
  onChangeC: (c: number) => void;
  minC?: number;
  maxC?: number;
  usesFahrenheit?: boolean;
  disabled?: boolean;
  running?: boolean;
  onStart: () => void;
  onStop: () => void;
  startLabel?: string;
  loadingStart?: boolean;
  loadingStop?: boolean;
};

export function ClimateDial({
  tempC,
  onChangeC,
  minC = MIN_DEFAULT,
  maxC = MAX_DEFAULT,
  usesFahrenheit = false,
  disabled = false,
  running = false,
  onStart,
  onStop,
  startLabel,
  loadingStart = false,
  loadingStop = false,
}: ClimateDialProps): JSX.Element {
  const span = maxC - minC;
  const t = Math.min(maxC, Math.max(minC, tempC));
  const pct = span <= 0 ? 0 : (t - minC) / span;

  const R = 88;
  const CX = 110;
  const CY = 110;
  const STROKE = 14;
  const C = 2 * Math.PI * R;
  const arcLen = C * ARC;
  const filled = arcLen * pct;

  const display = formatTemp(t, usesFahrenheit);
  const unit = usesFahrenheit ? "Fahrenheit" : "Celsius";
  const label = startLabel ?? (running ? `Restart at ${display}°` : "Start");

  const step = (dir: 1 | -1) => {
    if (disabled) return;
    const next = Math.min(maxC, Math.max(minC, Math.round((t + dir * STEP) * 2) / 2));
    if (next !== t) onChangeC(next);
  };

  return (
    <div className="glass rounded-2xl p-6 flex flex-col items-center gap-5">
      {/* ── Dial ring + center readout + steppers ───────────────── */}
      <div className="relative flex items-center justify-center gap-4">
        {/* − stepper */}
        <button
          type="button"
          aria-label="Decrease temperature"
          onClick={() => step(-1)}
          disabled={disabled || t <= minC}
          className="z-10 flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-iv-border bg-iv-surface/60 text-iv-text transition-colors hover:border-iv-cyan hover:text-iv-cyan disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-iv-border disabled:hover:text-iv-text"
        >
          <Minus className="h-5 w-5" />
        </button>

        {/* SVG ring */}
        <div className="relative h-[240px] w-[240px]">
          <svg
            viewBox="0 0 220 220"
            className="h-full w-full"
            aria-hidden="true"
            focusable="false"
          >
            <defs>
              <linearGradient id="iv-climate-ring" x1="0%" y1="100%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="var(--iv-cyan)" />
                <stop offset="50%" stopColor="var(--iv-green)" />
                <stop offset="100%" stopColor="var(--iv-warning)" />
              </linearGradient>
            </defs>

            {/* Track */}
            <circle
              cx={CX}
              cy={CY}
              r={R}
              fill="none"
              stroke="var(--iv-border)"
              strokeWidth={STROKE}
              strokeLinecap="round"
              strokeDasharray={`${arcLen} ${C - arcLen}`}
              transform={`rotate(${ROTATE} ${CX} ${CY})`}
            />

            {/* Value arc */}
            <circle
              cx={CX}
              cy={CY}
              r={R}
              fill="none"
              stroke="url(#iv-climate-ring)"
              strokeWidth={STROKE}
              strokeLinecap="round"
              strokeDasharray={`${filled} ${C - filled}`}
              transform={`rotate(${ROTATE} ${CX} ${CY})`}
            />
          </svg>

          {/* Center readout (non-interactive) */}
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-xs font-medium uppercase tracking-wider text-iv-muted">
              Temperature
            </span>
            <span className="mt-1 text-5xl font-semibold tabular-nums leading-none text-iv-text">
              {display}°
            </span>
            <span className="mt-1.5 text-xs text-iv-muted">{unit}</span>
          </div>

          {/* Defrost / windshield mark — sits in the bottom ring gap */}
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2">
            <div className="flex h-9 w-9 items-center justify-center rounded-full border border-iv-border bg-iv-surface">
              <Wind className="h-4 w-4 text-iv-cyan" />
            </div>
          </div>
        </div>

        {/* + stepper */}
        <button
          type="button"
          aria-label="Increase temperature"
          onClick={() => step(1)}
          disabled={disabled || t >= maxC}
          className="z-10 flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-iv-border bg-iv-surface/60 text-iv-text transition-colors hover:border-iv-cyan hover:text-iv-cyan disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-iv-border disabled:hover:text-iv-text"
        >
          <Plus className="h-5 w-5" />
        </button>
      </div>

      {/* ── Start / Stop ────────────────────────────────────────── */}
      <div className="flex w-full items-center justify-center gap-3">
        <button
          type="button"
          onClick={onStart}
          disabled={disabled || loadingStart}
          className="inline-flex min-w-[9.5rem] items-center justify-center gap-2 rounded-full bg-iv-green px-6 py-3 text-sm font-semibold text-white shadow-sm transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loadingStart ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Power className="h-4 w-4" />
          )}
          {loadingStart ? "Starting…" : label}
        </button>

        <button
          type="button"
          onClick={onStop}
          disabled={disabled || (!running && !loadingStop)}
          className="inline-flex min-w-[7rem] items-center justify-center gap-2 rounded-full border border-iv-border px-6 py-3 text-sm font-semibold text-iv-text transition-colors hover:bg-iv-surface disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
        >
          {loadingStop ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Power className="h-4 w-4" />
          )}
          {loadingStop ? "Stopping…" : "Stop"}
        </button>
      </div>
    </div>
  );
}
