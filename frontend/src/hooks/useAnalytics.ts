import { useQuery } from '@tanstack/react-query';
import {
  fetchDashboardProjects,
  fetchDashboardNormWork,
  fetchDashboardCategories,
} from '../api/analytics';
import { getEmployees } from '../api/employees';
import type { QuarterPeriod } from '../types/api';

export const useEmployeesForFilter = () =>
  useQuery({ queryKey: ['employees'], queryFn: () => getEmployees() });

export function useDashboardProjects(period: QuarterPeriod, teams?: Record<string, string>) {
  return useQuery({
    queryKey: ['dashboard-projects', period, teams],
    queryFn: ({ signal }) => fetchDashboardProjects(period, teams, signal),
    staleTime: 30_000,
    retry: 1,
  });
}

export function useDashboardNormWork(period: QuarterPeriod, teams?: Record<string, string>) {
  return useQuery({
    queryKey: ['dashboard-norm-work', period, teams],
    queryFn: ({ signal }) => fetchDashboardNormWork(period, teams, signal),
    staleTime: 30_000,
    retry: 1,
  });
}

export function useDashboardCategories(period: QuarterPeriod, teams?: Record<string, string>) {
  return useQuery({
    queryKey: ['dashboard-categories', period, teams],
    queryFn: ({ signal }) => fetchDashboardCategories(period, teams, signal),
    staleTime: 30_000,
    retry: 1,
  });
}
