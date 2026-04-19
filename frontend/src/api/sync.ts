import { api, BASE_URL } from './client';
import { pushError } from '../utils/errorStore';
import type {
  ConnectionTestResponse, SyncResponse, SyncStatusResponse,
  JiraProjectItem, JiraEpicItem,
  WorklogReloadRequest, WorklogReloadResponse,
  JiraUserSearchResult,
} from '../types/api';

export const testConnection = () => api.get<ConnectionTestResponse>('/sync/test-connection');
export const syncProjects = (signal?: AbortSignal) =>
  api.post<SyncResponse>('/sync/projects', undefined, signal);
export const syncIssues = (
  body?: { project_keys?: string[]; incremental?: boolean },
  signal?: AbortSignal,
) => api.post<SyncResponse>('/sync/issues', body, signal);
export const syncWorklogs = (signal?: AbortSignal) =>
  api.post<SyncResponse>('/sync/worklogs', undefined, signal);
export const reloadWorklogs = (req: WorklogReloadRequest, signal?: AbortSignal) =>
  api.post<WorklogReloadResponse>('/sync/worklogs/reload', req, signal);

// ─── SSE-стрим прогресса reload ──────────────────────────────────
// Событие ``progress`` прилетает после каждого обработанного issue
// (backend коммитит партию и шлёт текущие счётчики). ``done`` — финальные
// stats. Кнопка «Прервать» рвёт соединение через AbortSignal, backend
// ловит disconnect и шлёт ``cancelled`` (до разрыва, best-effort).

export type WorklogReloadProgress = {
  type: 'progress';
  deleted: number;
  issues_scanned: number;
  worklogs_inserted: number;
  current_key: string | null;
};

export type WorklogReloadDone = {
  type: 'done';
  deleted: number;
  issues_scanned: number;
  worklogs_inserted: number;
};

type WorklogReloadEvent =
  | WorklogReloadProgress
  | WorklogReloadDone
  | { type: 'error'; detail: string }
  | { type: 'cancelled' };

export async function reloadWorklogsStream(
  req: WorklogReloadRequest,
  onProgress: (e: WorklogReloadProgress) => void,
  signal?: AbortSignal,
): Promise<WorklogReloadDone> {
  const url = `${BASE_URL}/sync/worklogs/reload/stream`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(req),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e;
    pushError({
      ts: new Date().toISOString(), method: 'POST', url,
      status: null, detail: (e as Error).message,
      requestBody: JSON.stringify(req),
    });
    throw e;
  }
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail || res.statusText;
    pushError({
      ts: new Date().toISOString(), method: 'POST', url,
      status: res.status, detail,
      requestBody: JSON.stringify(req),
    });
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let final: WorklogReloadDone | null = null;
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
        const payload = JSON.parse(line.slice(5).trim()) as WorklogReloadEvent;
        if (payload.type === 'progress') onProgress(payload);
        else if (payload.type === 'done') final = payload;
        else if (payload.type === 'error') throw new Error(payload.detail);
        else if (payload.type === 'cancelled') {
          const err = new Error('Sync cancelled by client');
          err.name = 'AbortError';
          throw err;
        }
      }
    }
  }
  if (!final) throw new Error('Stream ended without done event');
  return final;
}
export const syncComments = (signal?: AbortSignal) =>
  api.post<SyncResponse>('/sync/comments', undefined, signal);
export const syncFull = (
  body?: { project_keys?: string[]; incremental?: boolean },
  signal?: AbortSignal,
) => api.post<SyncResponse>('/sync/full', body, signal);
export const refreshIssuesByKeys = (jiraKeys: string[], signal?: AbortSignal) =>
  api.post<SyncResponse>('/sync/issues/refresh', { jira_keys: jiraKeys }, signal);
export const syncTeams = (teams: string[], signal?: AbortSignal) =>
  api.post<SyncResponse>('/sync/teams', { teams }, signal);
export const getSyncStatus = () => api.get<SyncStatusResponse[]>('/sync/status');

// Browse Jira
export const getJiraProjects = (search?: string, team?: string) =>
  api.get<JiraProjectItem[]>('/sync/jira-projects', { search, team });
export const getJiraEpics = (projectKey: string, search?: string) =>
  api.get<JiraEpicItem[]>('/sync/jira-epics', { project_key: projectKey, search });

// Field discovery
export const getJiraFields = () =>
  api.get<JiraFieldItem[]>('/sync/jira-fields');
export const getJiraTeams = () =>
  api.get<string[]>('/sync/jira-teams');
export const getJiraIssueTypes = () =>
  api.get<string[]>('/sync/jira-issuetypes');

export const searchJiraUsers = (query: string) =>
  api.get<JiraUserSearchResult[]>('/jira/users/search', { query });

import type { JiraFieldItem } from '../types/api';
