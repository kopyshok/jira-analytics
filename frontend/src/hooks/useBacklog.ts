import { useQuery, useMutation, useMutationState, useQueryClient } from '@tanstack/react-query';
import {
  getBacklogItems,
  createBacklogItem,
  updateBacklogItem,
  deleteBacklogItem,
  linkJira,
  unlinkJira,
  refreshFromJiraStream,
  type BacklogRefreshProgress,
  type BacklogRefreshDone,
  archiveBacklogItem,
  restoreBacklogItem,
  setBacklogIncluded,
} from '../api/backlog';
import { getProjects } from '../api/projects';
import { choosePlanSource, type PlanChoiceBody } from '../api/issues';
import type { BacklogView } from '../types/api';

export const useProjects = () =>
  useQuery({ queryKey: ['projects'], queryFn: getProjects });

export const useBacklogItems = (
  view: BacklogView = 'active',
  teams?: string,
  subgroups?: string,
) =>
  useQuery({
    queryKey: ['backlog', view, teams, subgroups],
    queryFn: () => getBacklogItems(view, undefined, teams, subgroups),
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

type RefreshInput = {
  onProgress?: (e: BacklogRefreshProgress) => void;
  signal?: AbortSignal;
  /** Обновить только эти задачи; пусто — весь список. */
  keys?: string[];
};
export const useRefreshFromJira = () => {
  const qc = useQueryClient();
  return useMutation<BacklogRefreshDone, Error, RefreshInput | void>({
    mutationFn: (input) =>
      refreshFromJiraStream(
        input?.onProgress ?? (() => {}), input?.signal, input?.keys,
      ),
    onSuccess: () => {
      invalidateAllBacklog(qc);
      qc.invalidateQueries({ queryKey: ['planning', 'scenarios'] });
    },
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

const SET_INCLUDED_KEY = ['backlog', 'set-included'];

/** Галочка «В план»: выключенная задача не попадает в сценарии.
 *  `onError` — на весь хук: колбэк из `mutate` при нескольких строках
 *  в полёте срабатывает только у последней. */
export const useSetBacklogIncluded = (onError?: (e: Error) => void) => {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SET_INCLUDED_KEY,
    onError,
    mutationFn: ({ id, included }: { id: string; included: boolean }) =>
      setBacklogIncluded(id, included),
    // Ждём свежий список: иначе переключатель на миг отскакивает к старому значению.
    // После отказа тоже: сервер мог заблокировать включение, пока список был открыт.
    onSettled: () => Promise.all([
      qc.invalidateQueries({ queryKey: ['backlog'] }),
      qc.invalidateQueries({ queryKey: ['planning'] }),
    ]),
  });
};

/** Выбор значения по спорной оценке. Ждём свежий список: иначе спорная
 *  ячейка ещё мгновение висит после «Принять». */
export const useChoosePlanSource = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ issueId, body }: { issueId: string; body: PlanChoiceBody }) =>
      choosePlanSource(issueId, body),
    onSuccess: (_d, { issueId }) => {
      qc.invalidateQueries({ queryKey: ['planning'] });
      qc.invalidateQueries({ queryKey: ['hours-breakdown'] });
      qc.invalidateQueries({ queryKey: ['plan-history', issueId] });
      qc.invalidateQueries({ queryKey: ['plan-conflicts', issueId] });
      return qc.invalidateQueries({ queryKey: ['backlog'] });
    },
  });
};

/** Задачи, чья галочка «В план» сейчас сохраняется. */
export const useBacklogIncludedPending = (): Set<string> => {
  const ids = useMutationState({
    filters: { mutationKey: SET_INCLUDED_KEY, status: 'pending' },
    select: (m) => (m.state.variables as { id: string } | undefined)?.id,
  });
  return new Set(ids.filter((id): id is string => !!id));
};
