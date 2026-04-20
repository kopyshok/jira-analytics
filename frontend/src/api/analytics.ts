import { api, boolParam } from './client';
import type { AggregateRowResponse, ContextSwitchRowResponse } from '../types/api';

export type TeamFilterParams = {
  teams?: string;
  match_employees?: boolean;
  match_issues?: boolean;
};

const buildParams = (
  start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams,
) => ({
  start, end,
  employee_id: employeeId,
  project_key: projectKey,
  teams: team?.teams,
  match_employees: boolParam(team?.match_employees),
  match_issues: boolParam(team?.match_issues),
});

export const getHoursByEmployee = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  api.get<AggregateRowResponse[]>('/analytics/hours/by-employee', buildParams(start, end, employeeId, projectKey, team));

export const getHoursByProject = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  api.get<AggregateRowResponse[]>('/analytics/hours/by-project', buildParams(start, end, employeeId, projectKey, team));

export const getHoursByCategory = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  api.get<AggregateRowResponse[]>('/analytics/hours/by-category', buildParams(start, end, employeeId, projectKey, team));

export const getHoursByPeriod = (period: string, start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  api.get<AggregateRowResponse[]>('/analytics/hours/by-period', { period, ...buildParams(start, end, employeeId, projectKey, team) });

export const getContextSwitching = (start?: string, end?: string, employeeId?: string, projectKey?: string, team?: TeamFilterParams) =>
  api.get<ContextSwitchRowResponse[]>('/analytics/context-switching', buildParams(start, end, employeeId, projectKey, team));
