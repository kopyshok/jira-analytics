import { api } from './client';
import type { ScenarioResponse, PlanningResultResponse, StoredAllocationResponse } from '../types/api';

export const getScenarios = (year?: string, quarter?: string) =>
  api.get<ScenarioResponse[]>('/planning/scenarios', { year, quarter });

export const getScenario = (id: string) =>
  api.get<ScenarioResponse>(`/planning/scenarios/${id}`);

export const deleteScenario = (id: string) => api.del(`/planning/scenarios/${id}`);

export const getScenarioAllocations = (id: string) =>
  api.get<StoredAllocationResponse[]>(`/planning/scenarios/${id}/allocations`);

export const generateScenario = (data: { name: string; year: number; quarter: number }) =>
  api.post<PlanningResultResponse>('/planning/scenarios/generate', data);
