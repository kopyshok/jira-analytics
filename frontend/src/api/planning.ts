import { api } from './client';
import type { ScenarioResponse, PlanningResultResponse, StoredAllocationResponse } from '../types/api';
import type { CapacityPreviewRequest, CapacityPreviewResponse } from '../types/planning';

export const getScenarios = (year?: string, quarter?: string) =>
  api.get<ScenarioResponse[]>('/planning/scenarios', { year, quarter });

export const getScenario = (id: string) =>
  api.get<ScenarioResponse>(`/planning/scenarios/${id}`);

export const deleteScenario = (id: string) => api.del(`/planning/scenarios/${id}`);

export const getScenarioAllocations = (id: string) =>
  api.get<StoredAllocationResponse[]>(`/planning/scenarios/${id}/allocations`);

export const generateScenario = (data: {
  name: string;
  year: number;
  quarter: number;
  backlog_item_ids?: string[];
}) => api.post<PlanningResultResponse>('/planning/scenarios/generate', data);

export const capacityPreview = (body: CapacityPreviewRequest) =>
  api.post<CapacityPreviewResponse>('/planning/capacity-preview', body);
