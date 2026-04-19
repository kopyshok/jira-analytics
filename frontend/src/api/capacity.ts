import { api } from './client';
import type { CapacityRuleResponse, QuarterCapacityResponse, CategoryBreakdownResponse } from '../types/api';

// Capacity Rules
export const getCapacityRules = (year?: string) =>
  api.get<CapacityRuleResponse[]>('/capacity/rules', { year });
export const addCapacityRule = (data: { year: number; month: number; percent_of_norm: number }) =>
  api.post<CapacityRuleResponse>('/capacity/rules', data);
export const removeCapacityRule = (id: string) => api.del(`/capacity/rules/${id}`);

// Capacity Reports
export const getTeamCapacity = (year: string, quarter: string) =>
  api.get<QuarterCapacityResponse[]>('/capacity/team', { year, quarter });

export const getCategoryBreakdown = (year: number, quarter: number) =>
  api.get<CategoryBreakdownResponse[]>(
    '/capacity/team/category-breakdown',
    { year: String(year), quarter: String(quarter) },
  );
