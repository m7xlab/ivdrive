"use client";

import React from "react";
import type { MetricItem } from "./messageParts";

/**
 * Compact tiles for the key figures of an answer: label, value with its own unit,
 * optional note. Replaces the one-chart-with-everything-in-it that used to follow
 * every numeric answer.
 */
export function MetricsRenderer({ items }: { items: MetricItem[] }) {
  if (!items || items.length === 0) return null;
  const cols = items.length === 1 ? "grid-cols-1" : "grid-cols-2";
  return (
    <div className={`grid ${cols} gap-2 mt-3`} role="list" aria-label="Key figures">
      {items.map((m, i) => (
        <div
          key={`${m.label}-${i}`}
          role="listitem"
          className="rounded-xl border border-iv-border bg-iv-surface/60 px-3 py-2 min-w-0"
        >
          <div className="text-[11px] uppercase tracking-wide text-iv-muted truncate">{m.label}</div>
          <div className="flex items-baseline gap-1 mt-0.5">
            <span className="text-base font-semibold text-iv-text tabular-nums leading-tight">{m.value}</span>
            {m.unit ? <span className="text-xs text-iv-muted">{m.unit}</span> : null}
          </div>
          {m.note ? <div className="text-[11px] text-iv-muted mt-0.5 truncate">{m.note}</div> : null}
        </div>
      ))}
    </div>
  );
}
