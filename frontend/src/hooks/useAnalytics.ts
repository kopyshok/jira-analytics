import { useQuery } from '@tanstack/react-query';
import {
  getHoursByEmployee,
  getHoursByProject,
  getHoursByCategory,
  getHoursByPeriod,
  getContextSwitching,
  fetchDashboardProjects,
  fetchDashboardNormWork,
  fetchDashboardCategories,
  type TeamFilterParams,
} from '../api/analytics';
import { getEmployees } from '../api/employees';
import { getProjects } from '../api/projects';
import type { QuarterPeriod } from '../types/api';

const teamKey = (t?: TeamFilterParams) => [t?.teams ?? '', t?.match_employees ?? true, t?.match_issues ?? true];

export const useHoursByEmployee = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  useQuery({ queryKey: ['analytics', 'by-employee', start, end, employeeId, projectKey, ...teamKey(team)], queryFn: () => getHoursByEmployee(start, end, employeeId, projectKey, team) });

export const useHoursByProject = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  useQuery({ queryKey: ['analytics', 'by-project', start, end, employeeId, projectKey, ...teamKey(team)], queryFn: () => getHoursByProject(start, end, employeeId, projectKey, team) });

export const useHoursByCategory = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  useQuery({ queryKey: ['analytics', 'by-category', start, end, employeeId, projectKey, ...teamKey(team)], queryFn: () => getHoursByCategory(start, end, employeeId, projectKey, team) });

export const useHoursByPeriod = (period: string, start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  useQuery({ queryKey: ['analytics', 'by-period', period, start, end, employeeId, projectKey, ...teamKey(team)], queryFn: () => getHoursByPeriod(period, start, end, employeeId, projectKey, team) });

export const useContextSwitching = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  useQuery({ queryKey: ['analytics', 'context-switching', start, end, employeeId, projectKey, ...teamKey(team)], queryFn: () => getContextSwitching(start, end, employeeId, projectKey, team) });

export const useEmployeesForFilter = () =>
  useQuery({ queryKey: ['employees'], queryFn: () => getEmployees() });

export const useProjectsForFilter = () =>
  useQuery({ queryKey: ['projects'], queryFn: () => getProjects() });

export function useDashboardProjects(period: QuarterPeriod) {
  return useQuery({
    queryKey: ['dashboard-projects', period],
    queryFn: ({ signal }) => fetchDashboardProjects(period, signal),
    staleTime: 30_000,
    retry: 1,
  });
}

export function useDashboardNormWork(period: QuarterPeriod) {
  return useQuery({
    queryKey: ['dashboard-norm-work', period],
    queryFn: ({ signal }) => fetchDashboardNormWork(period, signal),
    staleTime: 30_000,
    retry: 1,
  });
}

export function useDashboardCategories(period: QuarterPeriod) {
  return useQuery({
    queryKey: ['dashboard-categories', period],
    queryFn: ({ signal }) => fetchDashboardCategories(period, signal),
    staleTime: 30_000,
    retry: 1,
  });
}
