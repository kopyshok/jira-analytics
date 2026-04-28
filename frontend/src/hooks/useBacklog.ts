import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getBacklogItems,
  createBacklogItem,
  updateBacklogItem,
  deleteBacklogItem,
  linkJira,
  unlinkJira,
  refreshFromJira,
  archiveBacklogItem,
  restoreBacklogItem,
} from '../api/backlog';
import { getProjects } from '../api/projects';
import type { BacklogView } from '../types/api';

export const useProjects = () =>
  useQuery({ queryKey: ['projects'], queryFn: getProjects });

export const useBacklogItems = (view: BacklogView = 'active', teams?: string) =>
  useQuery({
    queryKey: ['backlog', view, teams],
    queryFn: () => getBacklogItems(view, undefined, teams),
  });

function invalidateAllBacklog(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ['backlog'] });
}

export const useCreateBacklogItem = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createBacklogItem,
    onSuccess: () => invalidateAllBacklog(qc),
  });
};

export const useUpdateBacklogItem = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateBacklogItem>[1] }) =>
      updateBacklogItem(id, data),
    onSuccess: () => invalidateAllBacklog(qc),
  });
};

export const useDeleteBacklogItem = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteBacklogItem,
    onSuccess: () => {
      invalidateAllBacklog(qc);
      qc.invalidateQueries({ queryKey: ['planning', 'scenarios'] });
    },
  });
};

export const useLinkJira = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, jira_key }: { id: string; jira_key: string }) =>
      linkJira(id, jira_key),
    onSuccess: () => invalidateAllBacklog(qc),
  });
};

export const useUnlinkJira = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unlinkJira(id),
    onSuccess: () => invalidateAllBacklog(qc),
  });
};

export const useRefreshFromJira = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: refreshFromJira,
    onSuccess: () => invalidateAllBacklog(qc),
  });
};

export const useArchiveBacklogItem = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: archiveBacklogItem,
    onSuccess: () => invalidateAllBacklog(qc),
  });
};

export const useRestoreBacklogItem = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: restoreBacklogItem,
    onSuccess: () => invalidateAllBacklog(qc),
  });
};
