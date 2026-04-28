import { api } from './client';
import type { AllocationResponse, ScenarioResponse, ResourceBase, ScenarioRuleOut, ScenarioRuleInput } from '../types/api';

export const getScenarios = (year?: string, quarter?: string, status?: 'draft' | 'approved', teams?: string) =>
  api.get<ScenarioResponse[]>('/planning/scenarios', { year, quarter, status, teams });

export const getScenario = (id: string) =>
  api.get<ScenarioResponse>(`/planning/scenarios/${id}`);

export const createScenario = (data: { name: string; year: number; quarter: number; team: string }) =>
  api.post<ScenarioResponse>('/planning/scenarios', data);

export const updateScenario = (
  id: string,
  data: { name?: string; team?: string | null; external_qa_hours?: number | null },
) => api.patch<ScenarioResponse>(`/planning/scenarios/${id}`, data);

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

export const getScenarioResource = (sid: string) =>
  api.get<ResourceBase>(`/planning/scenarios/${sid}/resource`);

export const getScenarioRules = (sid: string) =>
  api.get<ScenarioRuleOut[]>(`/planning/scenarios/${sid}/rules`);

export const putScenarioRules = (sid: string, rules: ScenarioRuleInput[]) =>
  api.put<ScenarioRuleOut[]>(`/planning/scenarios/${sid}/rules`, { rules });

export const patchAllocationAssignee = (
  scenarioId: string,
  allocId: string,
  assigneeEmployeeId: string | null,
): Promise<AllocationResponse> =>
  api.patch<AllocationResponse>(
    `/planning/scenarios/${scenarioId}/allocations/${allocId}/assignee`,
    { assignee_employee_id: assigneeEmployeeId },
  );

export const reorderAllocations = (
  scenarioId: string,
  orderedIds: string[],
): Promise<AllocationResponse[]> =>
  api.patch<AllocationResponse[]>(
    `/planning/scenarios/${scenarioId}/allocations/reorder`,
    { ordered_ids: orderedIds },
  );
