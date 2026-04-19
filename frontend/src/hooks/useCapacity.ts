import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getCapacityRules, addCapacityRule, removeCapacityRule, getTeamCapacity, getCategoryBreakdown } from '../api/capacity';
import { getEmployees, recalcActiveEmployees, addEmployeeFromJira, replaceEmployeeTeams, setEmployeePrimaryTeam, patchEmployee } from '../api/employees';
import { searchJiraUsers } from '../api/sync';
import { api } from '../api/client';
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

export const useCapacityRules = () =>
  useQuery({ queryKey: ['capacity', 'rules'], queryFn: () => getCapacityRules() });

export const useAddCapacityRule = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: addCapacityRule, onSuccess: () => qc.invalidateQueries({ queryKey: ['capacity'] }) });
};

export const useRemoveCapacityRule = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: removeCapacityRule, onSuccess: () => qc.invalidateQueries({ queryKey: ['capacity'] }) });
};

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

export const useCopyRules = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { from_year: number; from_quarter: number; to_year: number; to_quarter: number }) =>
      api.post<{ created: number }>('/capacity/rules/copy-to-quarter', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['capacity', 'rules'] }),
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
