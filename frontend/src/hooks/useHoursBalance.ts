import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useGlobalTeamFilter } from './useGlobalTeamFilter';
import { useAppearanceSettings } from '../contexts/AppearanceContext';
import type {
  HoursBalanceResponse,
  HoursBalanceDetailResponse,
} from '../types/api';

export function useHoursBalance() {
  const { selectedTeams } = useGlobalTeamFilter();
  const appearance = useAppearanceSettings();
  const lagDays = appearance.hours_balance_lag_days;
  return useQuery<HoursBalanceResponse>({
    queryKey: ['dashboard', 'hours-balance', selectedTeams, lagDays],
    queryFn: ({ signal }) => {
      const params: Record<string, string> = { lag_days: String(lagDays) };
      if (selectedTeams.length > 0) params.teams = selectedTeams.join(',');
      return api.get<HoursBalanceResponse>(
        '/analytics/dashboard/hours-balance',
        params,
        signal,
      );
    },
    staleTime: 60_000,
    retry: 1,
  });
}

export function useHoursBalanceDetail(
  employeeId: string | null,
) {
  const { selectedTeams } = useGlobalTeamFilter();
  const appearance = useAppearanceSettings();
  const lagDays = appearance.hours_balance_lag_days;
  return useQuery<HoursBalanceDetailResponse>({
    queryKey: ['dashboard', 'hours-balance', 'detail', employeeId, lagDays, selectedTeams],
    queryFn: ({ signal }) => {
      const params: Record<string, string> = { lag_days: String(lagDays) };
      if (selectedTeams.length > 0) params.teams = selectedTeams.join(',');
      return api.get<HoursBalanceDetailResponse>(
        `/analytics/dashboard/hours-balance/${employeeId}`,
        params,
        signal,
      );
    },
    enabled: employeeId !== null,
    staleTime: 60_000,
    retry: 1,
  });
}
