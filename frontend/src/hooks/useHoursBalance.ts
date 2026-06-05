import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useGlobalTeamFilter } from './useGlobalTeamFilter';
import type {
  HoursBalanceResponse,
  HoursBalanceDetailResponse,
} from '../types/api';

export function useHoursBalance() {
  const { selectedTeams } = useGlobalTeamFilter();
  return useQuery<HoursBalanceResponse>({
    queryKey: ['dashboard', 'hours-balance', selectedTeams],
    queryFn: ({ signal }) =>
      api.get<HoursBalanceResponse>(
        '/analytics/dashboard/hours-balance',
        selectedTeams.length > 0 ? { teams: selectedTeams.join(',') } : {},
        signal,
      ),
    staleTime: 60_000,
    retry: 1,
  });
}

export function useHoursBalanceDetail(
  employeeId: string | null,
) {
  return useQuery<HoursBalanceDetailResponse>({
    queryKey: ['dashboard', 'hours-balance', 'detail', employeeId],
    queryFn: ({ signal }) =>
      api.get<HoursBalanceDetailResponse>(
        `/analytics/dashboard/hours-balance/${employeeId}`,
        {},
        signal,
      ),
    enabled: employeeId !== null,
    staleTime: 60_000,
    retry: 1,
  });
}
