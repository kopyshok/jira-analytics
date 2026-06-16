import { api, BASE_URL } from './client';
import { pushError } from '../utils/errorStore';
import type {
  BacklogItemResponse,
  BacklogImpactRisk,
  BacklogRefreshResult,
  BacklogView,
} from '../types/api';

export const getBacklogItems = (
  view: BacklogView = 'active',
  projectId?: string,
  teams?: string,
) =>
  api.get<BacklogItemResponse[]>('/backlog', { view, project_id: projectId, teams });

export const createBacklogItem = (data: {
  title: string;
  project_id?: string;
  team?: string;
  priority?: number;
  estimate_analyst_hours?: number;
  estimate_dev_hours?: number;
  estimate_qa_hours?: number;
  estimate_opo_hours?: number;
  opo_analyst_ratio?: number;
  impact?: BacklogImpactRisk;
  risk?: BacklogImpactRisk;
  parallel_count_analyst?: number;
  parallel_count_dev?: number;
  parallel_count_qa?: number;
}) => api.post<BacklogItemResponse>('/backlog', data);

export const updateBacklogItem = (id: string, data: Partial<{
  title: string;
  project_id: string;
  team: string | null;
  priority: number;
  estimate_analyst_hours: number;
  estimate_dev_hours: number;
  estimate_qa_hours: number;
  estimate_opo_hours: number;
  opo_analyst_ratio: number;
  impact: BacklogImpactRisk;
  risk: BacklogImpactRisk;
  assignee_employee_id: string | null;
  customer: string | null;
  parallel_count_analyst: number | null;
  parallel_count_dev: number | null;
  parallel_count_qa: number | null;
  involvement_analyst: number | null;
  involvement_dev: number | null;
  involvement_qa: number | null;
  involvement_launch: number | null;
  duration_analyst_days: number | null;
  duration_dev_days: number | null;
  duration_qa_days: number | null;
  duration_launch_days: number | null;
}>) => api.patch<BacklogItemResponse>(`/backlog/${id}`, data);

export interface DeleteBacklogResult {
  status: string;
  id: string;
  allocations_removed: number;
  affected_scenarios: { id: string; name: string }[];
}

export const deleteBacklogItem = (id: string) =>
  api.del<DeleteBacklogResult>(`/backlog/${id}`);

export const linkJira = (id: string, jira_key: string) =>
  api.post<BacklogItemResponse>(`/backlog/${id}/link-jira`, { jira_key });

export const unlinkJira = (id: string) =>
  api.post<BacklogItemResponse>(`/backlog/${id}/unlink-jira`);

// ─── SSE-стрим прогресса «Обновить с Jira» ───────────────────────
// ``progress`` прилетает по ходу похода в Jira (matched / total + ключ
// текущей задачи). ``done`` — финальные счётчики. Кнопка «Прервать» рвёт
// соединение через AbortSignal → backend шлёт ``cancelled``.

export type BacklogRefreshProgress = {
  type: 'progress';
  matched: number;
  total: number;
  current_key: string | null;
};

export type BacklogRefreshDone = { type: 'done' } & BacklogRefreshResult;

type BacklogRefreshEvent =
  | BacklogRefreshProgress
  | BacklogRefreshDone
  | { type: 'error'; detail: string }
  | { type: 'cancelled' };

export async function refreshFromJiraStream(
  onProgress: (e: BacklogRefreshProgress) => void,
  signal?: AbortSignal,
): Promise<BacklogRefreshDone> {
  const url = `${BASE_URL}/backlog/refresh-from-jira/stream`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      signal,
      credentials: 'include',
    });
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e;
    pushError({
      ts: new Date().toISOString(), method: 'POST', url,
      status: null, detail: (e as Error).message,
    });
    throw e;
  }
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail || res.statusText;
    pushError({
      ts: new Date().toISOString(), method: 'POST', url,
      status: res.status, detail,
    });
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let final: BacklogRefreshDone | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep = buffer.indexOf('\n\n');
    while (sep !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      sep = buffer.indexOf('\n\n');
      for (const line of raw.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const payload = JSON.parse(line.slice(5).trim()) as BacklogRefreshEvent;
        if (payload.type === 'progress') onProgress(payload);
        else if (payload.type === 'done') final = payload;
        else if (payload.type === 'error') throw new Error(payload.detail);
        else if (payload.type === 'cancelled') {
          const err = new Error('Refresh cancelled by client');
          err.name = 'AbortError';
          throw err;
        }
      }
    }
  }
  if (!final) throw new Error('Stream ended without done event');
  return final;
}

export const archiveBacklogItem = (id: string) =>
  api.post<BacklogItemResponse>(`/backlog/${id}/archive`);

export const restoreBacklogItem = (id: string) =>
  api.post<BacklogItemResponse>(`/backlog/${id}/restore`);
