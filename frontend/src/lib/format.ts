/**
 * Smart duration formatter — picks the most readable unit automatically.
 * - < 60 min       → "Xm"
 * - < 24 h (1440)  → "X.Xh"
 * - < 7 days       → "X.X days"
 * - < 30 days      → "X.X weeks"
 * - < 365 days     → "X.X months"
 * - ≥ 365 days     → "X.X years"
 */
export function formatSmartDuration(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes <= 0) return "—";

  if (minutes < 1) {
    const secs = Math.round(minutes * 60);
    return `${secs} sec`;
  }
  if (minutes < 60) {
    return `${Math.round(minutes)} min`;
  }
  if (minutes < 1440) {
    return `${(minutes / 60).toFixed(1)} hr`;
  }
  if (minutes < 10080) {
    return `${(minutes / 1440).toFixed(1)} days`;
  }
  if (minutes < 43200) {
    return `${(minutes / 10080).toFixed(1)} weeks`;
  }
  if (minutes < 525600) {
    return `${(minutes / 43200).toFixed(1)} months`;
  }
  return `${(minutes / 525600).toFixed(1)} years`;
}

/**
 * Classic h/m formatter — keeps minutes granularity for short durations.
 */
export function formatDuration(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes <= 0) return "—";
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}
