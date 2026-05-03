import { api } from './client';
import type {
  QuarterCapacityResponse,
  MandatoryWorkType,
  MandatoryWorkTypeCreate,
  MandatoryWorkTypeUpdate,
  RoleCapacityRule,
  EmployeeCapacityOverride,
  CopyRulesRequest,
  CopyRulesResponse,
} from '../types/api';

// Capacity Reports
export const getTeamCapacity = (year: string, quarter: string, teams?: string) => {
  const params: Record<string, string> = { year, quarter };
  if (teams) params.teams = teams;
  return api.get<QuarterCapacityResponse[]>('/capacity/team', params);
};

// === Mandatory work types (справочник) ===

export const getMandatoryWorkTypes = (is_active?: boolean) =>
  api.get<MandatoryWorkType[]>(
    '/mandatory-work-types',
    is_active !== undefined ? { is_active: String(is_active) } : undefined,
  );

export const createMandatoryWorkType = (body: MandatoryWorkTypeCreate) =>
  api.post<MandatoryWorkType>('/mandatory-work-types', body);

export const updateMandatoryWorkType = (id: string, body: MandatoryWorkTypeUpdate) =>
  api.patch<MandatoryWorkType>(`/mandatory-work-types/${id}`, body);

export const deleteMandatoryWorkType = (id: string) =>
  api.del<void>(`/mandatory-work-types/${id}`);

export const reorderMandatoryWorkTypes = (ids: string[]) =>
  api.post<MandatoryWorkType[]>('/mandatory-work-types/reorder', { ids });

// === Role capacity rules ===

export const getRoleCapacityRules = (year: number, quarter: number) =>
  api.get<RoleCapacityRule[]>(
    '/capacity/role-rules',
    { year: String(year), quarter: String(quarter) },
  );

export const copyRoleCapacityRulesToQuarter = (body: CopyRulesRequest) =>
  api.post<CopyRulesResponse>('/capacity/role-rules/copy-to-quarter', body);

// === Employee capacity overrides ===

export const getEmployeeCapacityOverrides = (params: {
  year: number; quarter: number; employee_id?: string;
}) => {
  const qp: Record<string, string> = {
    year: String(params.year),
    quarter: String(params.quarter),
  };
  if (params.employee_id) qp.employee_id = params.employee_id;
  return api.get<EmployeeCapacityOverride[]>('/capacity/employee-overrides', qp);
};

// === Team recalc ===

export const recalcTeamCapacity = (params: { year: number; quarter: number; team: string }) =>
  api.post<{ updated_employees: number; year: number; quarter: number; team: string; recalculated_at: string }>(
    `/capacity/team/recalc?year=${params.year}&quarter=${params.quarter}&team=${encodeURIComponent(params.team)}`,
  );
