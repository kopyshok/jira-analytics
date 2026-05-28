export interface UsageEvent {
  event_type: 'page_view' | 'heartbeat' | 'action';
  path: string;
  action_type?: string;
  entity_id?: string;
  at: string;
}

interface UsageSenderOpts {
  endpoint: string;
  flushIntervalMs: number;
  capacity?: number;
}

const DEFAULT_CAPACITY = 100;
const FLUSH_DEBOUNCE_MS = 1_500;

export class UsageSender {
  private buffer: UsageEvent[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;
  private firstFlushTimer: ReturnType<typeof setTimeout> | null = null;
  private opts: Required<UsageSenderOpts>;

  constructor(opts: UsageSenderOpts) {
    this.opts = { capacity: DEFAULT_CAPACITY, ...opts };
    if (opts.flushIntervalMs > 0) {
      this.timer = setInterval(() => void this.flushNow(), opts.flushIntervalMs);
    }
  }

  enqueue(ev: UsageEvent): void {
    if (this.buffer.length >= this.opts.capacity) return;
    this.buffer.push(ev);
    if (this.firstFlushTimer === null) {
      this.firstFlushTimer = setTimeout(() => {
        this.firstFlushTimer = null;
        void this.flushNow();
      }, FLUSH_DEBOUNCE_MS);
    }
  }

  bufferSize(): number {
    return this.buffer.length;
  }

  async flushNow(): Promise<void> {
    if (this.buffer.length === 0) return;
    const batch = this.buffer.splice(0, this.buffer.length);
    try {
      const res = await fetch(this.opts.endpoint, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ events: batch }),
      });
      if (!res.ok) {
        console.warn('[usage] POST /usage/events failed:', res.status, res.statusText);
      }
    } catch (e) {
      console.warn('[usage] POST /usage/events network error:', e);
    }
  }

  flushBeacon(): void {
    if (this.buffer.length === 0) return;
    const batch = this.buffer.splice(0, this.buffer.length);
    const body = new Blob(
      [JSON.stringify({ events: batch })],
      { type: 'application/json' },
    );
    navigator.sendBeacon?.(this.opts.endpoint, body);
  }

  dispose(): void {
    if (this.timer) clearInterval(this.timer);
    if (this.firstFlushTimer) clearTimeout(this.firstFlushTimer);
    this.timer = null;
    this.firstFlushTimer = null;
  }
}

function _resolveEndpoint(): string {
  const base = import.meta.env.VITE_API_BASE_URL || '/api/v1';
  return `${base.replace(/\/$/, '')}/usage/events`;
}

export const usageSender = new UsageSender({
  endpoint: _resolveEndpoint(),
  flushIntervalMs: 30_000,
});

if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => usageSender.flushBeacon());
  window.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') usageSender.flushBeacon();
  });
}
