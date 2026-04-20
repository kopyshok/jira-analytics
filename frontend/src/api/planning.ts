import { api } from './client';
import type { AllocationResponse, ScenarioResponse } from '../types/api';
import type { CapacityPreviewRequest, CapacityPreviewResponse } from '../types/planning';

export const getScenarios = (year?: string, quarter?: string, status?: 'draft' | 'approved') =>
  api.get<ScenarioResponse[]>('/planning/scenarios', { year, quarter, status });

export const getScenario = (id: string) =>
  api.get<ScenarioResponse>(`/planning/scenarios/${id}`);

export const createScenario = (data: { name: string; year: number; quarter: number }) =>
  api.post<ScenarioResponse>('/planning/scenarios', data);

export const updateScenario = (id: string, data: { name?: string }) =>
  api.patch<ScenarioResponse>(`/planning/scenarios/${id}`, data);

export const deleteScenario = (id: string) => api.del(`/planning/scenarios/${id}`);

export const approveScenario = (id: string) =>
  api.post<ScenarioResponse>(`/planning/scenarios/${id}/approve`);

export const revertScenario = (id: string) =>
  api.post<ScenarioResponse>(`/planning/scenarios/${id}/revert-to-draft`);

export const syncScenarioBacklog = (id: string) =>
  api.post<AllocationResponse[]>(`/planning/scenarios/${id}/sync-backlog`);

export const getScenarioAllocations = (id: string) =>
  api.get<AllocationResponse[]>(`/planning/scenarios/${id}/allocations`);

export const patchAllocation = (
  scenarioId: string,
  allocId: string,
  data: { included?: boolean; planned_hours?: number },
) => api.patch<AllocationResponse>(
  `/planning/scenarios/${scenarioId}/allocations/${allocId}`, data,
);

export const capacityPreview = (body: CapacityPreviewRequest) =>
  api.post<CapacityPreviewResponse>('/planning/capacity-preview', body);
