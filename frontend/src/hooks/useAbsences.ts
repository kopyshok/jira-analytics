import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAbsences, addAbsence, removeAbsence } from '../api/absences';
import { api } from '../api/client';
import type { AbsenceResponse } from '../types/api';

const KEY = ['capacity', 'absences'];

export const useAbsences = () =>
  useQuery({ queryKey: KEY, queryFn: () => getAbsences() });

export const useAddAbsence = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: addAbsence,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['capacity'] }),
  });
};

export const useRemoveAbsence = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: removeAbsence,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['capacity'] }),
  });
};

export function useAddAbsencesBatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: {
      employee_ids: string[];
      start_date: string;
      end_date: string;
      reason_id: string;
      hours_total?: number | null;
    }) => api.post<AbsenceResponse[]>('/capacity/absences/batch', b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['absences'] }),
  });
}
