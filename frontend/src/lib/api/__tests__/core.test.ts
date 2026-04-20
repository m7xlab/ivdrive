import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiFetch, ApiError, setAuthFlag, clearAuthFlag, hasAuthFlag, clearApiCache } from '../core';

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
      clone: () => ({ json: async () => mockErrorData }),
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
});
