import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getVacations, addVacation, removeVacation, getCapacityRules, addCapacityRule, removeCapacityRule, getTeamCapacity } from '../api/capacity';
import { getEmployees } from '../api/employees';

export const useEmployees = () =>
  useQuery({ queryKey: ['employees'], queryFn: () => getEmployees() });

export const useVacations = () =>
  useQuery({ queryKey: ['capacity', 'vacations'], queryFn: () => getVacations() });

export const useAddVacation = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: addVacation, onSuccess: () => qc.invalidateQueries({ queryKey: ['capacity'] }) });
};

export const useRemoveVacation = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: removeVacation, onSuccess: () => qc.invalidateQueries({ queryKey: ['capacity'] }) });
};

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
