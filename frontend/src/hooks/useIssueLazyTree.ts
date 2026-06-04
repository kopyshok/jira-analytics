import { useQuery, useMutation } from '@tanstack/react-query';
import {
  getTreeRoots,
  getTreeCounts,
  getIssueChildrenByTab,
  getEpicCandidates,
} from '../api/issues';

type Tab = 'stack' | 'active' | 'initiatives' | 'archive_target' | 'archive';

type RootsParams = {
  project_keys?: string;
  teams?: string;
  tab: Tab;
  search?: string;
};

export function useIssueRoots(params: RootsParams) {
  return useQuery({
    queryKey: ['issues', 'tree', 'roots', params],
    queryFn: ({ signal }) => getTreeRoots(params, signal),
    enabled: !!(params.teams || params.project_keys),
    retry: false,
    staleTime: 30_000,
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
      parentId, tab, teams, project_keys, search,
    }: { parentId: string; tab: Tab; teams?: string; project_keys?: string; search?: string }) =>
      getIssueChildrenByTab(parentId, tab, { teams, project_keys, search }),
  });
}
