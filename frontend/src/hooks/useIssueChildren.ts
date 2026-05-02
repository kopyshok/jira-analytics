import { useQuery } from '@tanstack/react-query';
import { getIssueChildren } from '../api/issues';

export function useIssueChildren(parentId: string | null | undefined, enabled = false) {
  return useQuery({
    queryKey: ['issue', 'children', parentId],
    queryFn: () => getIssueChildren(parentId!),
    enabled: enabled && !!parentId,
    staleTime: 30_000,
  });
}
