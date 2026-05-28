import { useEffect } from 'react';
import { useLocation } from 'react-router';
import { normalizePath } from './normalizePath';
import { usageSender } from './sender';

const HEARTBEAT_INTERVAL_MS = 30_000;

export function useHeartbeat(): void {
  const location = useLocation();
  useEffect(() => {
    const path = normalizePath(location.pathname);
    if (!path) return;

    const tick = () => {
      if (document.visibilityState !== 'visible') return;
      usageSender.enqueue({
        event_type: 'heartbeat',
        path,
        at: new Date().toISOString(),
      });
    };

    tick();
    const id = setInterval(tick, HEARTBEAT_INTERVAL_MS);
    return () => clearInterval(id);
  }, [location.pathname]);
}
