import { useQuery } from '@tanstack/react-query';
import { getIssueContext } from '../api/issues';

export function useIssueContext(issueId: string | null | undefined) {
  return useQuery({
    queryKey: ['issue', 'context', issueId],
    queryFn: () => getIssueContext(issueId!),
    enabled: !!issueId,
    staleTime: 30_000,
  });
}
