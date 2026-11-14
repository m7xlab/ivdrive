export const API_BASE =
  typeof process.env.NEXT_PUBLIC_API_URL === "string" &&
  process.env.NEXT_PUBLIC_API_URL.trim() !== ""
    ? process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, "")
    : "";

// localStorage can be missing (server render, a test without a stub) or throw (storage
// disabled in the browser); the flag is a hint, so those cases read as "not logged in".
export function setAuthFlag() {
  try {
    if (typeof window !== "undefined") localStorage.setItem("is_logged_in", "true");
  } catch {
    // ignore
  }
}

export function clearAuthFlag() {
  try {
    if (typeof window !== "undefined") localStorage.removeItem("is_logged_in");
  } catch {
    // ignore
  }
}

export function hasAuthFlag(): boolean {
  try {
    if (typeof window !== "undefined") return localStorage.getItem("is_logged_in") === "true";
  } catch {
    // ignore
  }
  return false;
}

export function clearTokens() {
  clearAuthFlag();
  // Deprecated: No longer used for localStorage, backend handles HttpOnly cookies.
}

// One refresh at a time. Several requests that notice an expired token together (page
// load, the sidebar poll and a dashboard query all at once) share the same refresh call
// instead of each rotating the token pair and the CSRF cookie underneath the others.
let refreshInFlight: Promise<boolean> | null = null;

export async function refreshAccessToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
      });
      return res.ok;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

// Refresh this many seconds before the access token lapses, so a request that is being
// prepared right now still carries a live token when it reaches the server.
const REFRESH_AHEAD_SECONDS = 30;

/** Unix seconds at which the access token expires, from the readable cookie the API sets. */
export function getAccessTokenExpiry(): number | null {
  const raw = getCookie("access_expires_at");
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : null;
}

/**
 * Refresh the session before a request if the access token is about to expire (or already
 * has). The API's access token lives 15 minutes and the client used to find out only by
 * sending a request and getting a 401 back, which the browser prints to the console on every
 * page left open for a while (the announcements poll was the usual first victim). With the
 * expiry known, no request is sent with a dead token. Returns false only when a refresh was
 * needed and failed.
 */
export async function ensureFreshAccessToken(): Promise<boolean> {
  if (!hasAuthFlag()) return true;
  const expiresAt = getAccessTokenExpiry();
  if (expiresAt === null) return true;
  const secondsLeft = expiresAt - Date.now() / 1000;
  if (secondsLeft > REFRESH_AHEAD_SECONDS) return true;
  const ok = await refreshAccessToken();
  if (!ok) clearAuthFlag();
  return ok;
}

export class ApiError extends Error {
  status: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}


// Simple memory cache for GET requests
const requestCache = new Map<string, { data: any; timestamp: number }>();
const CACHE_TTL_MS = 60000; // 1 minute

// Periodically clean up stale cache entries to prevent Map memory leaks over long sessions
if (typeof window !== "undefined") {
  // Prevent HMR from spawning multiple intervals
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  if (!(window as any).__apiCacheCleanupInterval) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).__apiCacheCleanupInterval = setInterval(() => {
      const now = Date.now();
      for (const [key, val] of requestCache.entries()) {
        if (now - val.timestamp >= CACHE_TTL_MS) {
          requestCache.delete(key);
        }
      }
    }, 120000); // Check every 2 minutes
  }
}

export async function clearApiCache() {
  requestCache.clear();
}

export function invalidateApiCache(vehicleId?: string) {
  if (!vehicleId) {
    requestCache.clear();
    return;
  }
  const matchString = `/api/v1/vehicles/${vehicleId}`;
  for (const key of requestCache.keys()) {
    // Using a simple substring match ensures environment-agnostic cache invalidation.
    // It cleanly avoids hardcoded origins (like localhost) and robustly handles 
    // both relative paths and absolute URLs across Docker, Helm, or production edge nodes.
    if (key.includes(matchString)) {
      requestCache.delete(key);
    }
  }
}

export function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
  if (match) return decodeURIComponent(match[2]);
  return null;
}

export async function apiFetch(
  path: string,
  options: RequestInit = {},
  signal?: AbortSignal,
): Promise<Response> {
  const method = options.method?.toUpperCase() || "GET";
  const isMutation = ["POST", "PUT", "PATCH", "DELETE"].includes(method);
  const isGet = method === "GET";
  const cacheKey = `${API_BASE}${path}`;

  // Serve from cache if fresh
  if (isGet) {
    const cached = requestCache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
      // Return a mocked Response object wrapped around the cached JSON
      const res = new Response(JSON.stringify(cached.data), {
        status: 200,
        statusText: "OK",
        headers: { "Content-Type": "application/json" },
      });
      // Force ok property in case polyfills miss it
      if (!('ok' in res)) {
        Object.defineProperty(res, 'ok', { get: () => true });
      }
      return res;
    }
  }

  // Refresh ahead of expiry so the request below never carries a dead token. Logout is the
  // one call that must go out as-is: a refresh there would only mint tokens to discard.
  if (path !== "/api/v1/auth/logout") {
    await ensureFreshAccessToken();
  }

  // Headers are built after the pre-emptive refresh: a refresh rotates the CSRF cookie.
  const buildHeaders = (): Record<string, string> => {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };
    if (isMutation) {
      const csrfToken = getCookie("csrf_token");
      if (csrfToken) h["X-CSRF-Token"] = csrfToken;
    }
    return h;
  };

  const fetchOptions: RequestInit = {
    ...options,
    headers: buildHeaders(),
    credentials: "include",
  };

  let res = await fetch(cacheKey, { ...fetchOptions, signal });

  if (res.status === 401) {
    // Fallback for a token that expired anyway (clock skew, a cookie cleared elsewhere):
    // refresh once and retry with headers rebuilt from the rotated cookies.
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      res = await fetch(cacheKey, { ...fetchOptions, headers: buildHeaders(), signal });
    } else {
      // If refresh failed, ensure client is marked as logged out.
      clearAuthFlag();
    }
  }

  // Standardize error handling: automatically throw if not OK.
  if (!res.ok && !options.headers?.hasOwnProperty('x-no-throw')) {
     const errorClone = res.clone();
     // Consume original body to avoid leaks
     try {
       await res.body?.cancel();
     } catch {
       // Ignore cancel errors
     }
     let errData;
     try {
       const textData = await errorClone.text();
       try {
         errData = JSON.parse(textData);
       } catch {
         errData = textData;
       }
     } catch {
       errData = "An error occurred";
     }
     
     const message = errData?.error?.message || errData?.detail || (typeof errData === 'string' ? errData : "An error occurred");
     throw new ApiError(message, res.status, errData);
  }

  // Invalidate cache on mutations
  if (options.method && ["POST", "PUT", "PATCH", "DELETE"].includes(options.method.toUpperCase()) && res.ok) {
    try {
      const parsedUrl = new URL(path, typeof window !== "undefined" ? window.location.origin : "http://localhost");
      const segments = parsedUrl.pathname.split("/").filter(Boolean);
      const vehicleIdIndex = segments.indexOf("vehicles") + 1;
      if (vehicleIdIndex > 0 && vehicleIdIndex < segments.length) {
        const vehicleId = segments[vehicleIdIndex];
        invalidateApiCache(vehicleId);
      } else {
        clearApiCache();
      }
    } catch {
      clearApiCache();
    }
  }

  if (isGet && res.ok) {
    const clone = res.clone();
    try {
      const data = await clone.json();
      requestCache.set(cacheKey, { data, timestamp: Date.now() });
    } catch {
      // Ignored for non-json
    }
  }
  return res;
}
