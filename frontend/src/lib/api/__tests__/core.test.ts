import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiFetch, ApiError, setAuthFlag, clearAuthFlag, hasAuthFlag, clearApiCache, getAccessTokenExpiry } from '../core';

describe('apiFetch core functionality', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn()
    });
    clearApiCache();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('performs successful GET request and caches it', async () => {
    const mockResponse = { data: 'test' };
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      clone: () => ({ json: async () => mockResponse }),
      json: async () => mockResponse
    } as any);

    const result = await apiFetch('/test');
    expect(result.ok).toBe(true);
    expect(fetch).toHaveBeenCalledTimes(1);

    // Second call should be cached (fetch not called again)
    const cachedResult = await apiFetch('/test');
    expect(cachedResult.ok).toBe(true);
    expect(fetch).toHaveBeenCalledTimes(1);
    
    const data = await cachedResult.json();
    expect(data).toEqual(mockResponse);
  });

  it('throws ApiError on non-OK response', async () => {
    const mockErrorData = { error: { message: 'Not found' } };
    
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 404,
      clone: () => ({ json: async () => mockErrorData, text: async () => JSON.stringify(mockErrorData) }),
      body: { cancel: vi.fn() },
      json: async () => mockErrorData
    } as any);

    await expect(apiFetch('/error')).rejects.toThrow(ApiError);
    await expect(apiFetch('/error')).rejects.toThrow('Not found');
  });

  it('attempts to refresh token on 401', async () => {
    const mockErrorData = { detail: 'Unauthorized' };
    
    // First call returns 401
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 401,
      clone: () => ({ json: async () => mockErrorData }),
      body: { cancel: vi.fn() },
      json: async () => mockErrorData
    } as any);
    
    // Refresh token call succeeds
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
    } as any);
    
    // Retry call succeeds
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      clone: () => ({ json: async () => ({}) }),
      json: async () => ({})
    } as any);

    const result = await apiFetch('/protected');
    expect(result.ok).toBe(true);
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  function okJson(data: unknown = {}) {
    return {
      ok: true,
      status: 200,
      clone: () => ({ json: async () => data }),
      json: async () => data,
    } as unknown as Response;
  }

  function unauthorized() {
    return {
      ok: false,
      status: 401,
      clone: () => ({ json: async () => ({ detail: 'Unauthorized' }), text: async () => '{"detail":"Unauthorized"}' }),
      body: { cancel: vi.fn() },
      json: async () => ({ detail: 'Unauthorized' }),
    } as unknown as Response;
  }

  function setCookie(name: string, value: string) {
    document.cookie = `${name}=${value}; path=/`;
  }

  function clearCookie(name: string) {
    document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  }

  describe('pre-emptive refresh from the access_expires_at cookie', () => {
    beforeEach(() => {
      vi.mocked(localStorage.getItem).mockImplementation((k: string) => (k === 'is_logged_in' ? 'true' : null));
    });

    afterEach(() => {
      clearCookie('access_expires_at');
      clearCookie('csrf_token');
    });

    it('reads the expiry cookie as unix seconds', () => {
      setCookie('access_expires_at', '1700000000');
      expect(getAccessTokenExpiry()).toBe(1700000000);
      clearCookie('access_expires_at');
      expect(getAccessTokenExpiry()).toBeNull();
    });

    it('refreshes before the request when the token is about to expire, so no 401 is ever sent', async () => {
      setCookie('access_expires_at', String(Math.floor(Date.now() / 1000) + 10));
      const calls: string[] = [];
      vi.mocked(fetch).mockImplementation(async (url: RequestInfo | URL) => {
        calls.push(String(url));
        return okJson({ fine: true });
      });

      const res = await apiFetch('/api/v1/notifications/announcements/active');
      expect(res.ok).toBe(true);
      expect(calls).toEqual(['/api/v1/auth/refresh', '/api/v1/notifications/announcements/active']);
    });

    it('does not refresh when the token has plenty of life left', async () => {
      setCookie('access_expires_at', String(Math.floor(Date.now() / 1000) + 600));
      const calls: string[] = [];
      vi.mocked(fetch).mockImplementation(async (url: RequestInfo | URL) => {
        calls.push(String(url));
        return okJson();
      });

      await apiFetch('/api/v1/auth/me');
      expect(calls).toEqual(['/api/v1/auth/me']);
    });

    it('builds the CSRF header after the pre-emptive refresh rotated the cookie', async () => {
      setCookie('access_expires_at', String(Math.floor(Date.now() / 1000) - 5));
      setCookie('csrf_token', 'stale');
      let sentCsrf: string | undefined;
      vi.mocked(fetch).mockImplementation(async (url: RequestInfo | URL, init?: RequestInit) => {
        if (String(url).endsWith('/auth/refresh')) {
          setCookie('csrf_token', 'rotated');
          return okJson();
        }
        sentCsrf = (init?.headers as Record<string, string> | undefined)?.['X-CSRF-Token'];
        return okJson();
      });

      await apiFetch('/api/v1/vehicles/v1/trips/t1', { method: 'PUT', body: '{}' });
      expect(sentCsrf).toBe('rotated');
    });

    it('does not refresh ahead of a logout call', async () => {
      setCookie('access_expires_at', String(Math.floor(Date.now() / 1000) - 5));
      const calls: string[] = [];
      vi.mocked(fetch).mockImplementation(async (url: RequestInfo | URL) => {
        calls.push(String(url));
        return okJson();
      });

      await apiFetch('/api/v1/auth/logout', { method: 'POST' });
      expect(calls).toEqual(['/api/v1/auth/logout']);
    });
  });

  it('shares one refresh between concurrent requests that all got 401', async () => {
    let refreshCalls = 0;
    let refreshed = false;
    vi.mocked(fetch).mockImplementation(async (url: RequestInfo | URL) => {
      if (String(url).endsWith('/auth/refresh')) {
        refreshCalls += 1;
        await new Promise((r) => setTimeout(r, 5));
        refreshed = true;
        return okJson();
      }
      return refreshed ? okJson() : unauthorized();
    });

    const results = await Promise.all([apiFetch('/a'), apiFetch('/b'), apiFetch('/c')]);
    expect(results.every((r) => r.ok)).toBe(true);
    expect(refreshCalls).toBe(1);
  });
});
