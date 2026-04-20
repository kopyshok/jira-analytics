import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { AbsenceReason } from '../types/api';

const KEY = ['absence-reasons'];

export function useAbsenceReasons() {
  return useQuery<AbsenceReason[]>({
    queryKey: KEY,
    queryFn: () => api.get<AbsenceReason[]>('/capacity/absence-reasons'),
    staleTime: 60_000,
  });
}

export function useCreateAbsenceReason() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: Omit<AbsenceReason, 'id'>) =>
      api.post<AbsenceReason>('/capacity/absence-reasons', b),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateAbsenceReason() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<AbsenceReason> }) =>
      api.patch<AbsenceReason>(`/capacity/absence-reasons/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteAbsenceReason() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del(`/capacity/absence-reasons/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useReorderAbsenceReasons() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) =>
      api.post<AbsenceReason[]>('/capacity/absence-reasons/reorder', { ids }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
