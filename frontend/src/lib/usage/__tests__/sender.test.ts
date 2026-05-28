import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { UsageSender } from '../sender';

describe('UsageSender', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ accepted: 1, rejected: 0 }) });
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  it('buffers events and flushes on demand', async () => {
    const s = new UsageSender({ endpoint: '/api/v1/usage/events', flushIntervalMs: 0 });
    s.enqueue({ event_type: 'page_view', path: '/dashboard', at: new Date().toISOString() });
    await s.flushNow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.events).toHaveLength(1);
  });

  it('drops events when buffer exceeds capacity', () => {
    const s = new UsageSender({ endpoint: '/x', flushIntervalMs: 0, capacity: 2 });
    s.enqueue({ event_type: 'page_view', path: '/dashboard', at: 'now' });
    s.enqueue({ event_type: 'page_view', path: '/dashboard', at: 'now' });
    s.enqueue({ event_type: 'page_view', path: '/dashboard', at: 'now' });
    expect(s.bufferSize()).toBe(2);
  });
});
