import { ApiError, apiFetch } from "./core";

const STORAGE_KEY = "ivdrive:geo:reverse";
const MIN_GAP_MS = 400;
const MAX_GAP_MS = 30_000;

export type ReverseGeocodeResult = {
  display_name: string;
  retry_after_seconds?: number | null;
};

const memory = new Map<string, string>();
const inflight = new Map<string, Promise<ReverseGeocodeResult>>();
const retryAfter = new Map<string, number>();

let gapMs = MIN_GAP_MS;
let failures = 0;
let queueTail: Promise<void> = Promise.resolve();
let persistTail: Promise<void> = Promise.resolve();

export function geoCoordKey(lat: number, lon: number): string {
  return `${Number(lat).toFixed(5)},${Number(lon).toFixed(5)}`;
}

function isUsefulName(name: unknown): name is string {
  return typeof name === "string" && name !== "Location" && name !== "Unknown Location";
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function expandWindow(seconds?: number | null): void {
  failures += 1;
  const fromServer = seconds && seconds > 0 ? seconds * 1000 : MIN_GAP_MS * 2 ** Math.min(failures, 6);
  gapMs = Math.min(MAX_GAP_MS, fromServer);
}

function resetWindow(): void {
  failures = 0;
  gapMs = MIN_GAP_MS;
}

function enqueue<T>(job: () => Promise<T>): Promise<T> {
  const run = queueTail.then(async () => {
    if (gapMs > 0) await sleep(gapMs);
    return job();
  });
  queueTail = run.then(() => undefined, () => undefined);
  return run;
}

function readStore(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (isUsefulName(value)) out[key] = value;
    }
    return out;
  } catch {
    return {};
  }
}

function readPersisted(key: string): string | null {
  if (typeof window === "undefined") return null;
  const stored = readStore()[key];
  if (isUsefulName(stored)) return stored;
  try {
    const legacy = window.sessionStorage.getItem(`geo_${key}`);
    if (isUsefulName(legacy)) return legacy;
  } catch {
    // ignore
  }
  return null;
}

function writePersisted(key: string, name: string): void {
  if (typeof window === "undefined" || !isUsefulName(name)) return;
  persistTail = persistTail.then(() => {
    try {
      const store = readStore();
      store[key] = name;
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
    } catch {
      // quota exceeded — memory cache still works this session
    }
  });
}

function remember(key: string, name: string): void {
  if (!isUsefulName(name)) return;
  memory.set(key, name);
  writePersisted(key, name);
}

async function requestName(latitude: number, longitude: number): Promise<ReverseGeocodeResult> {
  const key = geoCoordKey(latitude, longitude);
  try {
    const res = await apiFetch("/api/v1/geo/reverse", {
      method: "POST",
      body: JSON.stringify({ latitude, longitude }),
    });
    const data: unknown = await res.json();
    const record = data && typeof data === "object" ? (data as Record<string, unknown>) : {};
    const name = typeof record.display_name === "string" ? record.display_name : "Location";
    const retryAfterSeconds =
      typeof record.retry_after_seconds === "number" ? record.retry_after_seconds : null;
    if (isUsefulName(name)) {
      resetWindow();
      retryAfter.delete(key);
      remember(key, name);
      return { display_name: name, retry_after_seconds: null };
    }
    const retry = retryAfterSeconds ?? 8;
    expandWindow(retry);
    retryAfter.set(key, Date.now() + retry * 1000);
    return { display_name: "Location", retry_after_seconds: retry };
  } catch (error) {
    const retry = error instanceof ApiError && error.status === 429 ? 15 : 8;
    expandWindow(retry);
    retryAfter.set(key, Date.now() + retry * 1000);
    return { display_name: "Location", retry_after_seconds: retry };
  }
}

export const geoApi = {
  coordKey: geoCoordKey,

  peekReverseGeocode(latitude: number, longitude: number): string | null {
    const key = geoCoordKey(latitude, longitude);
    const hit = memory.get(key) ?? readPersisted(key);
    return isUsefulName(hit) ? hit : null;
  },

  async reverseGeocode(latitude: number, longitude: number): Promise<ReverseGeocodeResult> {
    const key = geoCoordKey(latitude, longitude);
    const cached = geoApi.peekReverseGeocode(latitude, longitude);
    if (cached) {
      remember(key, cached);
      return { display_name: cached, retry_after_seconds: null };
    }

    const until = retryAfter.get(key);
    if (until && Date.now() < until) {
      return {
        display_name: "Location",
        retry_after_seconds: Math.max(1, Math.ceil((until - Date.now()) / 1000)),
      };
    }

    const pending = inflight.get(key);
    if (pending) return pending;

    const request = enqueue(() => requestName(latitude, longitude)).finally(() => {
      inflight.delete(key);
    });
    inflight.set(key, request);
    return request;
  },
};
