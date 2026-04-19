import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getCapacityRules, addCapacityRule, removeCapacityRule, getTeamCapacity, getCategoryBreakdown } from '../api/capacity';
import { getEmployees, recalcActiveEmployees, addEmployeeFromJira } from '../api/employees';
import { searchJiraUsers } from '../api/sync';
import { api } from '../api/client';
import type {
  RecalcActiveResponse,
  EmployeeFromJiraRequest,
  EmployeeResponse,
} from '../types/api';

export const useEmployees = () =>
  useQuery({ queryKey: ['employees'], queryFn: () => getEmployees() });

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
