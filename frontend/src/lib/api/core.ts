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

export async function clearApiCache() {
  requestCache.clear();
}

export async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

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
      return new Response(JSON.stringify(cached.data), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
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
