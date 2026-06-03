import { useQuery } from '@tanstack/react-query';
import { getHoursBreakdown, type HoursBreakdownData } from '../api/issues';

export function useHoursBreakdown(issueId: string | null, year: number, quarter: number) {
  return useQuery<HoursBreakdownData>({
    queryKey: ['hours-breakdown', issueId, year, quarter],
    queryFn: () => getHoursBreakdown(issueId!, year, quarter),
    enabled: !!issueId && quarter >= 1 && quarter <= 4,
    staleTime: 30_000,
  });
}
