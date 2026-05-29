import { api } from './client';
import type {
  DashboardProjectsResponse,
  DashboardNormWorkResponse,
  DashboardCategoriesResponse,
  QuarterPeriod,
} from '../types/api';
import { periodToParams } from '../types/api';

export type TeamFilterParams = {
  teams?: string;
  match_employees?: boolean;
  match_issues?: boolean;
};

export function fetchDashboardProjects(
  period: QuarterPeriod,
  teams?: Record<string, string>,
  signal?: AbortSignal,
): Promise<DashboardProjectsResponse> {
  return api.get<DashboardProjectsResponse>(
    '/analytics/dashboard/projects',
    { ...periodToParams(period), ...(teams ?? {}) },
    signal,
  );
}

export function fetchDashboardNormWork(
  period: QuarterPeriod,
  teams?: Record<string, string>,
  signal?: AbortSignal,
): Promise<DashboardNormWorkResponse> {
  return api.get<DashboardNormWorkResponse>(
    '/analytics/dashboard/norm-work',
    { ...periodToParams(period), ...(teams ?? {}) },
    signal,
  );
}

export function fetchDashboardCategories(
  period: QuarterPeriod,
  teams?: Record<string, string>,
  signal?: AbortSignal,
): Promise<DashboardCategoriesResponse> {
  return api.get<DashboardCategoriesResponse>(
    '/analytics/dashboard/categories',
    { ...periodToParams(period), ...(teams ?? {}) },
    signal,
  );
}
