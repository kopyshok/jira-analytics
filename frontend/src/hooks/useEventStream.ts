import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { EVENTS_STREAM_URL, type GlobalEvent } from '../api/events';
import { useAuth } from './useAuth';

/**
 * Подключается к SSE-потоку /events/stream и инвалидирует кэши TanStack Query
 * по entity_changed событиям. Подключается один раз при монтировании AppLayout
 * и только если пользователь залогинен (иначе будет 401-спам).
 * При потере соединения переподключается через 5 секунд.
 *
 * Аутентификация через httpOnly cookie + EventSource(..., { withCredentials: true }).
 */
export function useEventStream() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const esRef = useRef<EventSource | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!user) return;
    let destroyed = false;

    function connect() {
      if (destroyed) return;
      const es = new EventSource(EVENTS_STREAM_URL, { withCredentials: true });
      esRef.current = es;

      es.onmessage = (e) => {
        if (!e.data || !e.data.trim()) return;
        try {
          const event = JSON.parse(e.data) as GlobalEvent;
          handleEvent(event, qc);
        } catch {
          /* ignore malformed */
        }
      };

      es.onerror = () => {
        es.close();
        esRef.current = null;
        if (!destroyed) {
          retryRef.current = setTimeout(connect, 5000);
        }
      };
    }

    connect();

    return () => {
      destroyed = true;
      if (retryRef.current) clearTimeout(retryRef.current);
      esRef.current?.close();
      esRef.current = null;
    };
  }, [qc, user]);
}

function handleEvent(event: GlobalEvent, qc: ReturnType<typeof useQueryClient>) {
  switch (event.type) {
    case 'entity_changed': {
      const entities = event.entities ?? (event.entity ? [event.entity] : []);
      entities.forEach((e) => invalidateForEntity(e, qc));
      break;
    }
    case 'pipeline_done':
      qc.invalidateQueries({ queryKey: ['sync', 'runs'] });
      qc.invalidateQueries({ queryKey: ['sync', 'status'] });
      break;
    case 'stage_done':
      qc.invalidateQueries({ queryKey: ['sync', 'runs'] });
      break;
    default:
      break;
  }
}

function invalidateForEntity(entity: string, qc: ReturnType<typeof useQueryClient>) {
  switch (entity) {
    case 'issues':
      qc.invalidateQueries({ queryKey: ['issues'] });
      qc.invalidateQueries({ queryKey: ['analytics'] });
      qc.invalidateQueries({ queryKey: ['backlog'] });
      qc.invalidateQueries({ queryKey: ['dashboard-projects'] });
      break;
    case 'backlog':
      qc.invalidateQueries({ queryKey: ['backlog'] });
      qc.invalidateQueries({ queryKey: ['planning'] });
      break;
    case 'planning':
      qc.invalidateQueries({ queryKey: ['planning'] });
      qc.invalidateQueries({ queryKey: ['backlog'] });
      qc.invalidateQueries({ queryKey: ['dashboard-projects'] });
      break;
    case 'worklogs':
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
      qc.invalidateQueries({ queryKey: ['analytics'] });
      qc.invalidateQueries({ queryKey: ['dashboard-projects'] });
      qc.invalidateQueries({ queryKey: ['dashboard-norm-work'] });
      qc.invalidateQueries({ queryKey: ['dashboard-categories'] });
      break;
    case 'capacity':
      qc.invalidateQueries({ queryKey: ['capacity'] });
      qc.invalidateQueries({ queryKey: ['capacity-diff'] });
      qc.invalidateQueries({ queryKey: ['planning'] });
      qc.invalidateQueries({ queryKey: ['dashboard-norm-work'] });
      break;
    case 'analytics':
      qc.invalidateQueries({ queryKey: ['analytics'] });
      qc.invalidateQueries({ queryKey: ['dashboard-projects'] });
      qc.invalidateQueries({ queryKey: ['dashboard-norm-work'] });
      qc.invalidateQueries({ queryKey: ['dashboard-categories'] });
      break;
    case 'employees':
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
      qc.invalidateQueries({ queryKey: ['dashboard-norm-work'] });
      break;
    case 'projects':
      qc.invalidateQueries({ queryKey: ['scope', 'projects'] });
      break;
    default:
      break;
  }
}
