import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getIssueTree, setIssueCategory, setIssueInclude, batchSetCategory } from '../api/issues';

export function useIssueTree(params?: { project_keys?: string; teams?: string }) {
  return useQuery({
    queryKey: ['issues', 'tree', params],
    queryFn: ({ signal }) => getIssueTree(params, signal),
    enabled: false,
    retry: false,
  });
}

function invalidateCategoryDependents(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
  // Backlog page and any allocation/scenario view update after
  // BacklogService.sync_from_issue on the backend runs.
  qc.invalidateQueries({ queryKey: ['backlog'] });
  qc.invalidateQueries({ queryKey: ['planning'] });
}

export function useSetIssueCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ issueId, categoryCode }: { issueId: string; categoryCode: string | null }) =>
      setIssueCategory(issueId, categoryCode),
    onSuccess: () => invalidateCategoryDependents(qc),
  });
}

export function useSetIssueInclude() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ issueId, include, recursive }: { issueId: string; include: boolean; recursive?: boolean }) =>
      setIssueInclude(issueId, include, recursive),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['issues', 'tree'] }),
  });
}

export function useBatchSetCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ issueIds, categoryCode }: { issueIds: string[]; categoryCode: string | null }) =>
      batchSetCategory(issueIds, categoryCode),
    onSuccess: () => invalidateCategoryDependents(qc),
  });
}
