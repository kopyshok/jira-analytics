import { useQuery } from '@tanstack/react-query';
import { fetchAnalyticsReport, type AnalyticsReportParams } from '../api/analyticsReport';

export function useAnalyticsReport(params: AnalyticsReportParams) {
  return useQuery({
    queryKey: ['analytics-report', params],
    queryFn: ({ signal }) => fetchAnalyticsReport(params, signal),
  });
}
