import { useEffect } from 'react';
import { useLocation } from 'react-router';
import { normalizePath } from './normalizePath';
import { usageSender } from './sender';

export function usePageView(): void {
  const location = useLocation();
  useEffect(() => {
    const path = normalizePath(location.pathname);
    if (!path) return;
    usageSender.enqueue({
      event_type: 'page_view',
      path,
      at: new Date().toISOString(),
    });
  }, [location.pathname]);
}
