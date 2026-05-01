import { useQuery } from '@tanstack/react-query';
import { fetchIssueWorklogs } from '../api/analyticsReport';

export function useIssueWorklogs(issueId: string | null, start: string, end: string) {
  return useQuery({
    queryKey: ['issue-worklogs', issueId, start, end],
    queryFn: ({ signal }) => fetchIssueWorklogs(issueId!, start, end, signal),
    enabled: !!issueId,
  });
}
