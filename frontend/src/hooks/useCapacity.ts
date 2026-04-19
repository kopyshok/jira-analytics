import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getTeamCapacity,
  getCategoryBreakdown,
  getMandatoryWorkTypes,
  createMandatoryWorkType,
  updateMandatoryWorkType,
  deleteMandatoryWorkType,
  reorderMandatoryWorkTypes,
  getRoleCapacityRules,
  createRoleCapacityRule,
  updateRoleCapacityRule,
  deleteRoleCapacityRule,
  copyRoleCapacityRulesToQuarter,
  getEmployeeCapacityOverrides,
  createEmployeeCapacityOverride,
  updateEmployeeCapacityOverride,
  deleteEmployeeCapacityOverride,
} from '../api/capacity';
import { getEmployees, recalcActiveEmployees, addEmployeeFromJira, replaceEmployeeTeams, setEmployeePrimaryTeam, patchEmployee } from '../api/employees';
import { searchJiraUsers } from '../api/sync';
import type {
  RecalcActiveResponse,
  EmployeeFromJiraRequest,
  EmployeeResponse,
  EmployeeRole,
} from '../types/api';

export const useEmployees = (params?: { withTeams?: boolean; isActive?: boolean }) =>
  useQuery({
    queryKey: ['employees', params?.withTeams ?? false, params?.isActive ?? null],
    queryFn: () => getEmployees({
      with_teams: params?.withTeams,
      is_active: params?.isActive,
    }),
    staleTime: 30_000,
  });

export const useTeamCapacity = (year: string, quarter: string) =>
  useQuery({
    queryKey: ['capacity', 'team', year, quarter],
    queryFn: () => getTeamCapacity(year, quarter),
    enabled: !!year && !!quarter,
  });

export const useCategoryBreakdown = (year: number, quarter: number) =>
  useQuery({
    queryKey: ['capacity', 'breakdown', year, quarter],
    queryFn: () => getCategoryBreakdown(year, quarter),
    staleTime: 30_000,
  });

export const useRecalcActiveEmployees = () => {
  const qc = useQueryClient();
  return useMutation<RecalcActiveResponse, Error, void>({
    mutationFn: recalcActiveEmployees,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};

export const useSearchJiraUsers = (query: string) =>
  useQuery({
    queryKey: ['jira', 'users', 'search', query],
    queryFn: () => searchJiraUsers(query),
    enabled: query.length >= 2,
    staleTime: 60_000,
  });

export const useAddEmployeeFromJira = () => {
  const qc = useQueryClient();
  return useMutation<EmployeeResponse, Error, EmployeeFromJiraRequest>({
    mutationFn: addEmployeeFromJira,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};

export const useSetEmployeeTeam = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, team }: { id: string; team: string | null }) =>
      api.put(`/employees/${id}/team`, { team }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};

export const useAutoDetectTeams = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<{ assigned: number; skipped: number; details: Array<{ employee_id: string; team: string }> }>(
        '/employees/auto-detect-teams',
        {},
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};

type EmployeesCtx = { snapshots: Array<[readonly unknown[], EmployeeResponse[] | undefined]> };

const patchEmployeesCache = (
  qc: ReturnType<typeof useQueryClient>,
  employeeId: string,
  mutate: (emp: EmployeeResponse) => EmployeeResponse,
): EmployeesCtx => {
  const queries = qc.getQueriesData<EmployeeResponse[]>({ queryKey: ['employees'] });
  const snapshots: EmployeesCtx['snapshots'] = [];
  for (const [key, data] of queries) {
    snapshots.push([key, data]);
    if (!data) continue;
    qc.setQueryData<EmployeeResponse[]>(key, data.map(e => e.id === employeeId ? mutate(e) : e));
  }
  return { snapshots };
};

const rollbackEmployeesCache = (
  qc: ReturnType<typeof useQueryClient>,
  ctx: EmployeesCtx | undefined,
) => {
  if (!ctx) return;
  for (const [key, data] of ctx.snapshots) qc.setQueryData(key, data);
};

export const useReplaceEmployeeTeams = () => {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { employeeId: string; teams: string[]; primary?: string }, EmployeesCtx>({
    mutationFn: ({ employeeId, teams, primary }) => replaceEmployeeTeams(employeeId, { teams, primary }),
    onMutate: async ({ employeeId, teams, primary }) => {
      await qc.cancelQueries({ queryKey: ['employees'] });
      const resolvedPrimary = primary ?? teams[0];
      return patchEmployeesCache(qc, employeeId, e => ({
        ...e,
        team: resolvedPrimary ?? null,
        teams: teams.map(t => ({ team: t, is_primary: t === resolvedPrimary })),
      }));
    },
    onError: (_err, _vars, ctx) => rollbackEmployeesCache(qc, ctx),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};

export const useUpdateEmployeeRole = () => {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { employeeId: string; role: EmployeeRole | null }, EmployeesCtx>({
    mutationFn: ({ employeeId, role }) => patchEmployee(employeeId, { role }),
    onMutate: async ({ employeeId, role }) => {
      await qc.cancelQueries({ queryKey: ['employees'] });
      return patchEmployeesCache(qc, employeeId, e => ({ ...e, role }));
    },
    onError: (_err, _vars, ctx) => rollbackEmployeesCache(qc, ctx),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
    },
  });
};

export const useSetPrimaryTeam = () => {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { employeeId: string; team: string }, EmployeesCtx>({
    mutationFn: ({ employeeId, team }) => setEmployeePrimaryTeam(employeeId, team),
    onMutate: async ({ employeeId, team }) => {
      await qc.cancelQueries({ queryKey: ['employees'] });
      return patchEmployeesCache(qc, employeeId, e => ({
        ...e,
        team,
        teams: (e.teams ?? []).map(t => ({ ...t, is_primary: t.team === team })),
      }));
    },
    onError: (_err, _vars, ctx) => rollbackEmployeesCache(qc, ctx),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};

// ──────────────── Mandatory work types ────────────────

export const useMandatoryWorkTypes = (params?: { isActive?: boolean }) =>
  useQuery({
    queryKey: ['mandatory-work-types', params?.isActive ?? null],
    queryFn: () => getMandatoryWorkTypes(params?.isActive),
    staleTime: 60_000,
  });

export const useCreateMandatoryWorkType = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createMandatoryWorkType,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['mandatory-work-types'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};

export const useUpdateMandatoryWorkType = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof updateMandatoryWorkType>[1] }) =>
      updateMandatoryWorkType(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['mandatory-work-types'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};

export const useDeleteMandatoryWorkType = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteMandatoryWorkType,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['mandatory-work-types'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};

export const useReorderMandatoryWorkTypes = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: reorderMandatoryWorkTypes,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['mandatory-work-types'] }),
  });
};

// ──────────────── Role capacity rules ────────────────

export const useRoleCapacityRules = (year: number, quarter: number) =>
  useQuery({
    queryKey: ['role-capacity-rules', year, quarter],
    queryFn: () => getRoleCapacityRules(year, quarter),
    enabled: Number.isFinite(year) && quarter >= 1 && quarter <= 4,
  });

export const useCreateRoleCapacityRule = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createRoleCapacityRule,
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ['role-capacity-rules', v.year, v.quarter] });
      qc.invalidateQueries({ queryKey: ['capacity', 'team'] });
    },
  });
};

export const useUpdateRoleCapacityRule = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, percent }: { id: string; percent: number; year: number; quarter: number }) =>
      updateRoleCapacityRule(id, { percent_of_norm: percent }),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ['role-capacity-rules', v.year, v.quarter] });
      qc.invalidateQueries({ queryKey: ['capacity', 'team'] });
    },
  });
};

export const useDeleteRoleCapacityRule = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string; year: number; quarter: number }) => deleteRoleCapacityRule(id),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ['role-capacity-rules', v.year, v.quarter] });
      qc.invalidateQueries({ queryKey: ['capacity', 'team'] });
    },
  });
};

export const useCopyRoleCapacityRulesToQuarter = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: copyRoleCapacityRulesToQuarter,
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ['role-capacity-rules', v.to_year, v.to_quarter] });
      qc.invalidateQueries({ queryKey: ['capacity', 'team'] });
    },
  });
};

// ──────────────── Employee capacity overrides ────────────────

export const useEmployeeCapacityOverrides = (params: {
  year: number; quarter: number; employeeId?: string;
}) =>
  useQuery({
    queryKey: ['employee-capacity-overrides', params.year, params.quarter, params.employeeId ?? null],
    queryFn: () => getEmployeeCapacityOverrides({
      year: params.year, quarter: params.quarter, employee_id: params.employeeId,
    }),
    enabled: Number.isFinite(params.year) && params.quarter >= 1 && params.quarter <= 4,
  });

export const useCreateEmployeeCapacityOverride = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createEmployeeCapacityOverride,
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ['employee-capacity-overrides', v.year, v.quarter] });
      qc.invalidateQueries({ queryKey: ['capacity', 'team'] });
    },
  });
};

export const useUpdateEmployeeCapacityOverride = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, percent }: { id: string; percent: number; year: number; quarter: number }) =>
      updateEmployeeCapacityOverride(id, { percent_of_norm: percent }),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ['employee-capacity-overrides', v.year, v.quarter] });
      qc.invalidateQueries({ queryKey: ['capacity', 'team'] });
    },
  });
};

export const useDeleteEmployeeCapacityOverride = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string; year: number; quarter: number }) => deleteEmployeeCapacityOverride(id),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ['employee-capacity-overrides', v.year, v.quarter] });
      qc.invalidateQueries({ queryKey: ['capacity', 'team'] });
    },
  });
};
