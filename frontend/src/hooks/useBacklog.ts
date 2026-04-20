import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getBacklogItems,
  createBacklogItem,
  updateBacklogItem,
  deleteBacklogItem,
  linkJira,
  unlinkJira,
  refreshFromJira,
} from '../api/backlog';
import { getProjects } from '../api/projects';

export const useProjects = () =>
  useQuery({ queryKey: ['projects'], queryFn: getProjects });

export const useBacklogItems = () =>
  useQuery({
    queryKey: ['backlog'],
    queryFn: () => getBacklogItems(),
  });

export const useCreateBacklogItem = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: createBacklogItem, onSuccess: () => qc.invalidateQueries({ queryKey: ['backlog'] }) });
};

export const useUpdateBacklogItem = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateBacklogItem>[1] }) => updateBacklogItem(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backlog'] }),
  });
};

export const useDeleteBacklogItem = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: deleteBacklogItem, onSuccess: () => qc.invalidateQueries({ queryKey: ['backlog'] }) });
};

export const useLinkJira = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, jira_key }: { id: string; jira_key: string }) => linkJira(id, jira_key),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backlog'] }),
  });
};

export const useUnlinkJira = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unlinkJira(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backlog'] }),
  });
};

export const useRefreshFromJira = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: refreshFromJira,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backlog'] }),
  });
};
