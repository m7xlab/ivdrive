/**
 * Compute the API `limit` parameter for /vehicles/<id>/statistics calls based on
 * the user's selected dateRange and the bucket period (day/week/month/year).
 *
 * Why this exists:
 * The /statistics endpoint applies the date filter (from_date / to_date) but
 * also applies a hard `limit` cap on the number of buckets returned. With a
 * small fixed limit (e.g. 30) and a long dateRange (e.g. 1 year, period=day),
 * the API silently returns only the most-recent ~30 buckets — the dashboard
 * then shows 30 days of data even though the user picked "Last 1 year".
 *
 * The fix is to size the limit to the selected window so one bucket per period
 * fits. The backend caps at 365 (Query(le=365)) so we clamp.
 *
 * Examples:
 *   period=day,   dateRange=30 days  -> limit=32
 *   period=day,   dateRange=365 days -> limit=365 (capped)
 *   period=week,  dateRange=365 days -> limit=53
 *   period=month, dateRange=365 days -> limit=13
 *   period=year,  dateRange=365 days -> limit=2
 *   period=day,   dateRange=1 day    -> limit=1
 *   period=year,  dateRange=10 years -> limit=10 (capped at 365)
 */
export type Period = "day" | "week" | "month" | "year";

/** Backend's hard cap on /statistics limit (Query(le=365)). */
export const MAX_STATISTICS_LIMIT = 365;

const PERIOD_DAYS: Record<Period, number> = {
  day: 1,
  week: 7,
  month: 30,
  year: 365,
};

export function calculateStatisticsLimit(
  period: Period,
  fromISO: string,
  toISO: string,
): number {
  const from = new Date(fromISO).getTime();
  const to = new Date(toISO).getTime();
  if (!Number.isFinite(from) || !Number.isFinite(to) || to < from) {
    // Degenerate input — return the smallest valid limit.
    return 1;
  }
  const msPerDay = 24 * 60 * 60 * 1000;
  const days = Math.max(1, Math.ceil((to - from) / msPerDay));
  const buckets = Math.ceil(days / PERIOD_DAYS[period]);
  // +2 to absorb DST shifts, timezone rounding, and inclusive end-date edges
  // so we don't truncate the first or last bucket.
  return Math.min(MAX_STATISTICS_LIMIT, Math.max(1, buckets + 2));
}