import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  testConnection, syncProjects, syncIssues, syncWorklogs, syncComments, syncFull,
  refreshIssuesByKeys, syncTeams, reloadWorklogs,
  getSyncStatus, getJiraProjects, getJiraEpics, getJiraFields, getJiraTeams,
  getJiraIssueTypes,
} from '../api/sync';
import { batchScopeProjects } from '../api/scope';
import { recalculateAll } from '../api/mapping';
import type { WorklogReloadRequest, WorklogReloadResponse } from '../types/api';

export const useConnectionTest = () =>
  useQuery({ queryKey: ['sync', 'connection'], queryFn: testConnection, retry: false, enabled: false });

export const useSyncStatus = () =>
  useQuery({ queryKey: ['sync', 'status'], queryFn: getSyncStatus });

type SyncBody = { project_keys?: string[]; incremental?: boolean } | undefined;

// Все sync-мутации принимают опциональный signal: AbortSignal — его прокидываем
// в fetch, чтобы кнопка «Прервать» на фронте могла оборвать HTTP-запрос;
// backend ловит disconnect и поднимает CancelledError → 499.
type SyncInput = { body?: SyncBody; signal?: AbortSignal };

export const useSyncMutation = (type: 'projects' | 'issues' | 'worklogs' | 'comments' | 'full') => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input?: SyncInput) => {
      const body = input?.body;
      const signal = input?.signal;
      switch (type) {
        case 'issues': return syncIssues(body, signal);
        case 'full': return syncFull(body, signal);
        case 'projects': return syncProjects(signal);
        case 'worklogs': return syncWorklogs(signal);
        case 'comments': return syncComments(signal);
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sync', 'status'] }),
  });
};

export const useRefreshIssuesByKeys = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ jiraKeys, signal }: { jiraKeys: string[]; signal?: AbortSignal }) =>
      refreshIssuesByKeys(jiraKeys, signal),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
      qc.invalidateQueries({ queryKey: ['sync', 'status'] });
    },
  });
};

export const useSyncTeams = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ teams, signal }: { teams: string[]; signal?: AbortSignal }) =>
      syncTeams(teams, signal),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
      qc.invalidateQueries({ queryKey: ['sync', 'status'] });
    },
  });
};

type ReloadInput = { req: WorklogReloadRequest; signal?: AbortSignal };
export const useReloadWorklogs = () => {
  const qc = useQueryClient();
  return useMutation<WorklogReloadResponse, Error, ReloadInput>({
    mutationFn: ({ req, signal }) => reloadWorklogs(req, signal),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};

export const useRecalculateMapping = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: recalculateAll,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['analytics'] }),
  });
};

// Browse Jira
export const useJiraProjects = (search?: string, team?: string) =>
  useQuery({
    queryKey: ['jira', 'projects', search, team],
    queryFn: () => getJiraProjects(search, team),
    enabled: false,  // manual trigger
    retry: false,
  });

export const useJiraFields = () =>
  useQuery({
    queryKey: ['jira', 'fields'],
    queryFn: getJiraFields,
    enabled: false,
    retry: false,
  });

export const useJiraTeams = () =>
  useQuery({
    queryKey: ['jira', 'teams'],
    queryFn: getJiraTeams,
    enabled: false,
    retry: false,
    staleTime: 60_000,
  });

export const useJiraIssueTypes = () =>
  useQuery({
    queryKey: ['jira', 'issuetypes'],
    queryFn: getJiraIssueTypes,
    retry: false,
    staleTime: 300_000,
  });

export const useJiraEpics = (projectKey: string, search?: string) =>
  useQuery({
    queryKey: ['jira', 'epics', projectKey, search],
    queryFn: () => getJiraEpics(projectKey, search),
    enabled: !!projectKey,
    retry: false,
  });

// Batch scope
export const useBatchScopeProjects = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: batchScopeProjects,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scope', 'projects'] });
    },
  });
};
