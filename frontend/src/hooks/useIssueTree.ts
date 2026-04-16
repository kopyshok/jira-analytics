import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getIssueTree, setIssueCategory, setIssueInclude } from '../api/issues';

export function useIssueTree(params?: { project_keys?: string; team?: string }) {
  return useQuery({
    queryKey: ['issues', 'tree', params],
    queryFn: () => getIssueTree(params),
    enabled: false,  // manual trigger via refetch
    retry: false,
  });
}

export function useSetIssueCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ issueId, categoryCode }: { issueId: string; categoryCode: string | null }) =>
      setIssueCategory(issueId, categoryCode),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['issues', 'tree'] }),
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
