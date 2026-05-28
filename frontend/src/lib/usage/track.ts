import { normalizePath } from './normalizePath';
import { usageSender } from './sender';

export function trackAction(actionType: string, entityId?: string): void {
  const path = normalizePath(window.location.pathname) ?? '/';
  usageSender.enqueue({
    event_type: 'action',
    action_type: actionType,
    entity_id: entityId,
    path,
    at: new Date().toISOString(),
  });
}
