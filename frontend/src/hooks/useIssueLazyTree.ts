import { useQuery, useMutation, keepPreviousData } from '@tanstack/react-query';
import {
  getTreeRoots,
  getTreeCounts,
  getIssueChildrenByTab,
  getEpicCandidates,
} from '../api/issues';
import type { RootsQuery, TriageTab } from '../utils/categoryTriage';

type Tab = TriageTab;

/** Ключ кэша страницы верхних строк — по нему же страницу кладут в кэш заранее. */
export const issueRootsKey = (params: RootsQuery) => ['issues', 'tree', 'roots', params] as const;

export function useIssueRoots(params: RootsQuery) {
  return useQuery({
    queryKey: issueRootsKey(params),
    queryFn: ({ signal }) => getTreeRoots(params, signal),
    enabled: !!(params.teams || params.project_keys),
    retry: false,
    staleTime: 30_000,
    // Пока грузится соседняя страница, на экране остаётся текущая.
    placeholderData: keepPreviousData,
  });
}

type CountsParams = { project_keys?: string; teams?: string };

export function useIssueTreeCounts(params: CountsParams) {
  return useQuery({
    queryKey: ['issues', 'tree', 'counts', params],
    queryFn: ({ signal }) => getTreeCounts(params, signal),
    enabled: !!(params.teams || params.project_keys),
    retry: false,
    staleTime: 30_000,
  });
}

export function useEpicCandidates(params: CountsParams) {
  return useQuery({
    queryKey: ['issues', 'tree', 'epic-candidates', params],
    queryFn: ({ signal }) => getEpicCandidates(params, signal),
    enabled: !!(params.teams || params.project_keys),
    retry: false,
    staleTime: 30_000,
  });
}

export function useLoadChildrenMutation() {
  return useMutation({
    mutationFn: ({
      parentId, tab, teams, project_keys, search, only_moved,
    }: {
      parentId: string; tab: Tab; teams?: string; project_keys?: string; search?: string; only_moved?: boolean;
    }) =>
      getIssueChildrenByTab(parentId, tab, { teams, project_keys, search, only_moved }),
  });
}
