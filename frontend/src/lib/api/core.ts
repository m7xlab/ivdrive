export const API_BASE =
  typeof process.env.NEXT_PUBLIC_API_URL === "string" &&
  process.env.NEXT_PUBLIC_API_URL.trim() !== ""
    ? process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, "")
    : "";

export function setAuthFlag() {
  if (typeof window !== "undefined") {
    localStorage.setItem("is_logged_in", "true");
  }
}

export function clearAuthFlag() {
  if (typeof window !== "undefined") {
    localStorage.removeItem("is_logged_in");
  }
}

export function hasAuthFlag(): boolean {
  if (typeof window !== "undefined") {
    return localStorage.getItem("is_logged_in") === "true";
  }
  return false;
}

export function clearTokens() {
  clearAuthFlag();
  // Deprecated: No longer used for localStorage, backend handles HttpOnly cookies.
}

export async function refreshAccessToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
    });
    return res.ok;
  } catch {
    return false;
  }
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
  options: RequestInit = {}
): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  const method = options.method?.toUpperCase() || "GET";
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const csrfToken = getCookie("csrf_token");
    if (csrfToken) {
      headers["X-CSRF-Token"] = csrfToken;
    }
  }

  const fetchOptions: RequestInit = {
    ...options,
    headers,
    credentials: "include",
  };

  const isGet = !options.method || options.method.toUpperCase() === "GET";
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

  let res = await fetch(cacheKey, fetchOptions);

  if (res.status === 401) {
    // Attempt to refresh cookie
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      // Retry
      res = await fetch(`${API_BASE}${path}`, fetchOptions);
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
       errData = await errorClone.json();
     } catch {
       errData = await errorClone.text();
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
