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

export class UsageSender {
  private buffer: UsageEvent[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;
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
  }

  bufferSize(): number {
    return this.buffer.length;
  }

  async flushNow(): Promise<void> {
    if (this.buffer.length === 0) return;
    const batch = this.buffer.splice(0, this.buffer.length);
    try {
      await fetch(this.opts.endpoint, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ events: batch }),
        keepalive: true,
      });
    } catch {
      // fire-and-forget; drop on failure
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
    this.timer = null;
  }
}

export const usageSender = new UsageSender({
  endpoint: `${import.meta.env.VITE_API_BASE_URL ?? '/api/v1'}/usage/events`,
  flushIntervalMs: 30_000,
});

if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => usageSender.flushBeacon());
}
