import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { InvolvementDefault } from '../types/api';

const KEY = 'involvement-defaults';

export function useInvolvementDefaults(team: string | null | undefined) {
  return useQuery({
    queryKey: [KEY, team ?? null],
    queryFn: () =>
      api.get<InvolvementDefault[]>(
        '/planning/involvement-defaults',
        team ? { team } : undefined,
      ),
    enabled: !!team,
  });
}

type CreateBody = Omit<InvolvementDefault, 'id'>;

export function useCreateInvolvementDefault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateBody) =>
      api.post<InvolvementDefault>('/planning/involvement-defaults', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  });
}

export function useUpdateInvolvementDefault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<CreateBody> }) =>
      api.patch<InvolvementDefault>(`/planning/involvement-defaults/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  });
}

export function useDeleteInvolvementDefault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.del(`/planning/involvement-defaults/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
  });
}
