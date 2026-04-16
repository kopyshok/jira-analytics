import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { testConnection, syncProjects, syncIssues, syncWorklogs, syncComments, syncFull, getSyncStatus } from '../api/sync';
import { recalculateAll } from '../api/mapping';

export const useConnectionTest = () =>
  useQuery({ queryKey: ['sync', 'connection'], queryFn: testConnection, retry: false, enabled: false });

export const useSyncStatus = () =>
  useQuery({ queryKey: ['sync', 'status'], queryFn: getSyncStatus });

export const useSyncMutation = (type: 'projects' | 'issues' | 'worklogs' | 'comments' | 'full') => {
  const qc = useQueryClient();
  const fns = { projects: syncProjects, issues: syncIssues, worklogs: syncWorklogs, comments: syncComments, full: syncFull };
  return useMutation({
    mutationFn: fns[type],
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sync', 'status'] }),
  });
};

export const useRecalculateMapping = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: recalculateAll,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['analytics'] }),
  });
};
