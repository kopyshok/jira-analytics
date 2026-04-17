import { api } from './client';
import type { ConnectionTestResponse, SyncResponse, SyncStatusResponse, JiraProjectItem, JiraEpicItem } from '../types/api';

export const testConnection = () => api.get<ConnectionTestResponse>('/sync/test-connection');
export const syncProjects = () => api.post<SyncResponse>('/sync/projects');
export const syncIssues = (body?: { project_keys?: string[]; incremental?: boolean }) => api.post<SyncResponse>('/sync/issues', body);
export const syncWorklogs = () => api.post<SyncResponse>('/sync/worklogs');
export const syncComments = () => api.post<SyncResponse>('/sync/comments');
export const syncFull = (body?: { project_keys?: string[]; incremental?: boolean }) => api.post<SyncResponse>('/sync/full', body);
export const refreshIssuesByKeys = (jiraKeys: string[]) =>
  api.post<SyncResponse>('/sync/issues/refresh', { jira_keys: jiraKeys });
export const syncTeams = (teams: string[]) =>
  api.post<SyncResponse>('/sync/teams', { teams });
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

import type { JiraFieldItem } from '../types/api';
