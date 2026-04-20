import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { authApi } from '../auth';
import * as core from '../core';

describe('authApi', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.spyOn(core, 'setAuthFlag').mockImplementation(() => {});
    vi.spyOn(core, 'clearAuthFlag').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('login calls correct endpoint and sets auth flag if no 2fa', async () => {
    const mockRes = { requires_2fa: false, access_token: 'test' };
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      clone: () => ({ json: async () => mockRes }),
      json: async () => mockRes
    } as any);

    const result = await authApi.login('test@test.com', 'password123');
    expect(result).toEqual(mockRes);
    expect(core.setAuthFlag).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/v1/auth/login'), expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ email: 'test@test.com', password: 'password123' })
    }));
  });

  it('logout calls endpoint and clears auth flag', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      clone: () => ({ json: async () => ({}) }),
      json: async () => ({})
    } as any);

    await authApi.logout();
    expect(core.clearAuthFlag).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/v1/auth/logout'), expect.objectContaining({
      method: 'POST'
    }));
  });
});
