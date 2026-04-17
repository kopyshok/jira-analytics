import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  testConnection, syncProjects, syncIssues, syncWorklogs, syncComments, syncFull,
  refreshIssuesByKeys, syncTeams,
  getSyncStatus, getJiraProjects, getJiraEpics, getJiraFields, getJiraTeams,
} from '../api/sync';
import { batchScopeProjects } from '../api/scope';
import { recalculateAll } from '../api/mapping';

export const useConnectionTest = () =>
  useQuery({ queryKey: ['sync', 'connection'], queryFn: testConnection, retry: false, enabled: false });

export const useSyncStatus = () =>
  useQuery({ queryKey: ['sync', 'status'], queryFn: getSyncStatus });

type SyncBody = { project_keys?: string[]; incremental?: boolean } | undefined;

export const useSyncMutation = (type: 'projects' | 'issues' | 'worklogs' | 'comments' | 'full') => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body?: SyncBody) => {
      switch (type) {
        case 'issues': return syncIssues(body);
        case 'full': return syncFull(body);
        case 'projects': return syncProjects();
        case 'worklogs': return syncWorklogs();
        case 'comments': return syncComments();
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sync', 'status'] }),
  });
};

export const useRefreshIssuesByKeys = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jiraKeys: string[]) => refreshIssuesByKeys(jiraKeys),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
      qc.invalidateQueries({ queryKey: ['sync', 'status'] });
    },
  });
};

export const useSyncTeams = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (teams: string[]) => syncTeams(teams),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
      qc.invalidateQueries({ queryKey: ['sync', 'status'] });
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
