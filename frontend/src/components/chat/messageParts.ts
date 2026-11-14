/**
 * Split an assistant message into renderable parts.
 *
 * The model may append fenced JSON blocks after its prose:
 *   ```json_metrics   — a handful of key figures, rendered as compact tiles
 *   ```json_chart     — one genuine series, rendered as a chart
 *   ```json_followups — two or three questions the user could ask next, rendered as buttons
 *
 * The API already validates these blocks (ai_presentation.py); this parser is tolerant
 * anyway so an older stored message or a block that slipped through still renders sanely.
 */

export interface MetricItem {
  label: string;
  value: string;
  unit?: string;
  note?: string;
}

export interface ChartSpec {
  title?: string;
  type: "bar" | "line" | "pie" | "donut";
  data: Record<string, unknown>[];
  categories: string[];
  xDataKey?: string;
}

export type MessagePart =
  | { type: "text"; content: string }
  | { type: "chart"; chart: ChartSpec }
  | { type: "metrics"; items: MetricItem[] }
  | { type: "followups"; questions: string[] };

const BLOCK_RE = /```(json_chart|json_metrics|json_followups)\s*([\s\S]*?)```/gi;

export const MIN_CHART_POINTS = 3;
export const MAX_FOLLOWUPS = 3;

function parseJson(payload: string): unknown {
  try {
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

function asNumber(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = Number(v.replace(/,/g, "").trim());
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function formatNumber(n: number): string {
  if (Number.isInteger(n)) return n.toLocaleString("en-GB").replace(/,/g, " ");
  return n.toLocaleString("en-GB", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).replace(/,/g, " ");
}

/** A chart is a real series when every point carries every category and there are enough points. */
export function isValidSeries(chart: ChartSpec | null): chart is ChartSpec {
  if (!chart || !Array.isArray(chart.data) || !Array.isArray(chart.categories) || chart.categories.length === 0) return false;
  if (!["bar", "line", "pie", "donut"].includes(chart.type)) return false;
  if (chart.data.length < MIN_CHART_POINTS) return false;
  const xKey = chart.xDataKey || "name";
  if (chart.type === "pie" || chart.type === "donut") {
    if (chart.categories.length !== 1) return false;
    const key = chart.categories[0];
    return chart.data.filter((row) => (asNumber(row?.[key]) ?? 0) !== 0).length >= 2;
  }
  return chart.data.every(
    (row) => row && typeof row === "object" && xKey in row && chart.categories.every((c) => asNumber(row[c]) !== null),
  );
}

/** Flatten a chart that is not a series into metric tiles (one per value). */
export function chartToMetrics(chart: ChartSpec): MetricItem[] {
  const xKey = chart.xDataKey || "name";
  const cats = Array.isArray(chart.categories) ? chart.categories : [];
  const items: MetricItem[] = [];
  for (const row of chart.data || []) {
    if (!row || typeof row !== "object") continue;
    const label = String(row[xKey] ?? "").trim();
    const keys = cats.filter((k) => k in row);
    const valueKeys = keys.length > 0 ? keys : Object.keys(row).filter((k) => k !== xKey);
    for (const key of valueKeys) {
      const n = asNumber(row[key]);
      if (n === null) continue;
      items.push({ label: label || key, value: formatNumber(n), unit: key === "value" ? "" : key });
    }
  }
  return items.slice(0, 8);
}

function toChart(payload: unknown): ChartSpec | null {
  if (!payload || typeof payload !== "object") return null;
  const c = payload as Partial<ChartSpec>;
  if (!Array.isArray(c.data) || !Array.isArray(c.categories)) return null;
  return {
    title: typeof c.title === "string" ? c.title : undefined,
    type: (typeof c.type === "string" ? c.type.toLowerCase() : "bar") as ChartSpec["type"],
    data: c.data.filter((r) => r && typeof r === "object") as Record<string, unknown>[],
    categories: c.categories.filter((k) => typeof k === "string") as string[],
    xDataKey: typeof c.xDataKey === "string" ? c.xDataKey : undefined,
  };
}

function toMetrics(payload: unknown): MetricItem[] {
  const raw = Array.isArray(payload) ? payload : (payload as { items?: unknown })?.items;
  if (!Array.isArray(raw)) return [];
  const items: MetricItem[] = [];
  for (const r of raw) {
    if (!r || typeof r !== "object") continue;
    const o = r as Record<string, unknown>;
    const label = String(o.label ?? "").trim();
    if (!label || o.value === undefined || o.value === null || o.value === "") continue;
    const n = asNumber(o.value);
    const item: MetricItem = {
      label: label.slice(0, 40),
      value: n !== null ? formatNumber(n) : String(o.value).slice(0, 24),
      unit: o.unit ? String(o.unit).slice(0, 16) : "",
    };
    if (o.note) item.note = String(o.note).slice(0, 80);
    items.push(item);
  }
  return items.slice(0, 8);
}

function toFollowups(payload: unknown): string[] {
  const raw = Array.isArray(payload) ? payload : (payload as { questions?: unknown })?.questions;
  if (!Array.isArray(raw)) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const q of raw) {
    if (typeof q !== "string") continue;
    const t = q.replace(/\s+/g, " ").trim();
    if (!t || t.length > 80 || seen.has(t.toLowerCase())) continue;
    seen.add(t.toLowerCase());
    out.push(t);
    if (out.length === MAX_FOLLOWUPS) break;
  }
  return out;
}

export function parseMessageContent(content: string): MessagePart[] {
  const parts: MessagePart[] = [];
  let lastIndex = 0;
  let chartShown = false;
  let followupsShown = false;
  BLOCK_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = BLOCK_RE.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: "text", content: content.substring(lastIndex, match.index) });
    }
    lastIndex = match.index + match[0].length;
    const kind = match[1].toLowerCase();
    const payload = parseJson(match[2]);
    if (kind === "json_chart") {
      const chart = toChart(payload);
      if (!chart) continue;
      if (isValidSeries(chart) && !chartShown) {
        chartShown = true;
        parts.push({ type: "chart", chart });
      } else {
        const items = chartToMetrics(chart);
        if (items.length > 0) parts.push({ type: "metrics", items });
      }
    } else if (kind === "json_metrics") {
      const items = toMetrics(payload);
      if (items.length > 0) parts.push({ type: "metrics", items });
    } else if (!followupsShown) {
      const questions = toFollowups(payload);
      if (questions.length > 0) {
        followupsShown = true;
        parts.push({ type: "followups", questions });
      }
    }
  }
  if (lastIndex < content.length) {
    parts.push({ type: "text", content: content.substring(lastIndex) });
  }
  // Trim whitespace-only text parts left around removed blocks.
  const cleaned = parts.filter((p) => p.type !== "text" || p.content.trim() !== "");
  return cleaned.length > 0 ? cleaned : [{ type: "text", content }];
}

/** The follow-up questions of a message, if it carries any. */
export function followupsOf(content: string): string[] {
  const part = parseMessageContent(content).find((p) => p.type === "followups");
  return part && part.type === "followups" ? part.questions : [];
}
