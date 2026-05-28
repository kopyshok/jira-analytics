import { afterEach, describe, expect, it, vi } from 'vitest';

describe('api client', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it('sends requests when API base URL is relative', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '/api/v1');
    vi.stubGlobal('window', { location: new URL('http://jira-analytics.api-n1.onyx.local/login') });
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"ok":true}', {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    const { api } = await import('./client');

    await api.post('/auth/login', { email: 'user@example.com', password: 'password' });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://jira-analytics.api-n1.onyx.local/api/v1/auth/login',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    );
  });
});
