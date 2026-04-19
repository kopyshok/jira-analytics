import { api } from './client';
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
