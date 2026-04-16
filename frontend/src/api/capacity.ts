import { api } from './client';
import type { VacationResponse, CapacityRuleResponse, QuarterCapacityResponse } from '../types/api';

// Vacations
export const getVacations = (employeeId?: string) =>
  api.get<VacationResponse[]>('/capacity/vacations', { employee_id: employeeId });
export const addVacation = (data: { employee_id: string; start_date: string; end_date: string; hours_total?: number }) =>
  api.post<VacationResponse>('/capacity/vacations', data);
export const removeVacation = (id: string) => api.del(`/capacity/vacations/${id}`);

// Capacity Rules
export const getCapacityRules = (year?: string) =>
  api.get<CapacityRuleResponse[]>('/capacity/rules', { year });
export const addCapacityRule = (data: { year: number; month: number; percent_of_norm: number }) =>
  api.post<CapacityRuleResponse>('/capacity/rules', data);
export const removeCapacityRule = (id: string) => api.del(`/capacity/rules/${id}`);

// Capacity Reports
export const getTeamCapacity = (year: string, quarter: string) =>
  api.get<QuarterCapacityResponse[]>('/capacity/team', { year, quarter });
