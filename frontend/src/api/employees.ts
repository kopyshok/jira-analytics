import { api } from './client';
import type { EmployeeResponse, RecalcActiveResponse, EmployeeFromJiraRequest } from '../types/api';

export const getEmployees = (isActive?: boolean) =>
  api.get<EmployeeResponse[]>('/employees', { is_active: isActive?.toString() });

export const recalcActiveEmployees = () =>
  api.post<RecalcActiveResponse>('/employees/recalc-active', {});

export const addEmployeeFromJira = (req: EmployeeFromJiraRequest) =>
  api.post<EmployeeResponse>('/employees/from-jira', req);
