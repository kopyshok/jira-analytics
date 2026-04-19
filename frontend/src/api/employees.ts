import { api } from './client';
import type { EmployeeResponse, EmployeeRole, EmployeeTeamItem, RecalcActiveResponse, EmployeeFromJiraRequest } from '../types/api';

export const getEmployees = (params?: { is_active?: boolean; with_teams?: boolean }) => {
  const qp: Record<string, string> = {};
  if (params?.is_active !== undefined) qp.is_active = String(params.is_active);
  if (params?.with_teams) qp.with_teams = 'true';
  return api.get<EmployeeResponse[]>('/employees', qp);
};

export const getEmployeeTeams = (employeeId: string) =>
  api.get<EmployeeTeamItem[]>(`/employees/${employeeId}/teams`);

export const replaceEmployeeTeams = (
  employeeId: string,
  body: { teams: string[]; primary?: string },
) => api.put<EmployeeTeamItem[]>(`/employees/${employeeId}/teams`, body);

export const setEmployeePrimaryTeam = (employeeId: string, team: string) =>
  api.put<EmployeeTeamItem[]>(`/employees/${employeeId}/teams/primary`, { team });

export const deleteEmployeeTeam = (employeeId: string, team: string) =>
  api.del<void>(`/employees/${employeeId}/teams/${encodeURIComponent(team)}`);

export const patchEmployee = (employeeId: string, body: { role?: EmployeeRole | null }) =>
  api.patch<EmployeeResponse>(`/employees/${employeeId}`, body);

export const recalcActiveEmployees = () =>
  api.post<RecalcActiveResponse>('/employees/recalc-active', {});

export const addEmployeeFromJira = (req: EmployeeFromJiraRequest) =>
  api.post<EmployeeResponse>('/employees/from-jira', req);
