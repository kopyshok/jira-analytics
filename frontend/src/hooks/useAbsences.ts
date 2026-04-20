import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAbsences, addAbsence, removeAbsence } from '../api/absences';
import { api } from '../api/client';
import type { AbsenceResponse } from '../types/api';

const KEY = ['capacity', 'absences'];

export const useAbsences = () =>
  useQuery({ queryKey: KEY, queryFn: () => getAbsences() });

// Add new absence to the cached list optimistically so the tag appears instantly;
// team-capacity is invalidated separately in background.
const appendToAbsenceCache = (
  qc: ReturnType<typeof useQueryClient>,
  created: AbsenceResponse[],
) => {
  qc.setQueryData<AbsenceResponse[]>(KEY, (old) => [...(old ?? []), ...created]);
};

const removeFromAbsenceCache = (
  qc: ReturnType<typeof useQueryClient>,
  id: string,
) => {
  qc.setQueryData<AbsenceResponse[]>(KEY, (old) =>
    (old ?? []).filter((a) => a.id !== id),
  );
};

export const useAddAbsence = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: addAbsence,
    onSuccess: (created) => {
      appendToAbsenceCache(qc, [created]);
      qc.invalidateQueries({ queryKey: ['capacity', 'team'] });
      qc.invalidateQueries({ queryKey: ['capacity', 'breakdown'] });
    },
  });
};

export const useRemoveAbsence = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: removeAbsence,
    onMutate: (id: string) => {
      const prev = qc.getQueryData<AbsenceResponse[]>(KEY);
      removeFromAbsenceCache(qc, id);
      return { prev };
    },
    onError: (_e, _id, ctx) => {
      if (ctx?.prev) qc.setQueryData(KEY, ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['capacity', 'team'] });
      qc.invalidateQueries({ queryKey: ['capacity', 'breakdown'] });
    },
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
    onSuccess: (created) => {
      appendToAbsenceCache(qc, created);
      qc.invalidateQueries({ queryKey: ['capacity', 'team'] });
      qc.invalidateQueries({ queryKey: ['capacity', 'breakdown'] });
    },
  });
}
