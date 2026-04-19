import { api } from './client';
import type {
  QuarterCapacityResponse,
  CategoryBreakdownResponse,
  MandatoryWorkType,
  MandatoryWorkTypeCreate,
  MandatoryWorkTypeUpdate,
  RoleCapacityRule,
  RoleCapacityRuleCreate,
  EmployeeCapacityOverride,
  EmployeeCapacityOverrideCreate,
  CopyRulesRequest,
  CopyRulesResponse,
} from '../types/api';

// Capacity Reports
export const getTeamCapacity = (year: string, quarter: string) =>
  api.get<QuarterCapacityResponse[]>('/capacity/team', { year, quarter });

export const getCategoryBreakdown = (year: number, quarter: number) =>
  api.get<CategoryBreakdownResponse[]>(
    '/capacity/team/category-breakdown',
    { year: String(year), quarter: String(quarter) },
  );

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

export const createRoleCapacityRule = (body: RoleCapacityRuleCreate) =>
  api.post<RoleCapacityRule>('/capacity/role-rules', body);

export const updateRoleCapacityRule = (id: string, body: { percent_of_norm: number }) =>
  api.patch<RoleCapacityRule>(`/capacity/role-rules/${id}`, body);

export const deleteRoleCapacityRule = (id: string) =>
  api.del<void>(`/capacity/role-rules/${id}`);

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

export const createEmployeeCapacityOverride = (body: EmployeeCapacityOverrideCreate) =>
  api.post<EmployeeCapacityOverride>('/capacity/employee-overrides', body);

export const updateEmployeeCapacityOverride = (
  id: string, body: { percent_of_norm: number },
) => api.patch<EmployeeCapacityOverride>(`/capacity/employee-overrides/${id}`, body);

export const deleteEmployeeCapacityOverride = (id: string) =>
  api.del<void>(`/capacity/employee-overrides/${id}`);
