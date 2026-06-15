import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listWorkDesks,
  createWorkDesk,
  updateWorkDeskWidgets,
  revokeWorkDesk,
  regenerateWorkDesk,
} from '../api/workDesks';

const KEY = ['work-desks'];

export const useWorkDesks = () =>
  useQuery({ queryKey: KEY, queryFn: () => listWorkDesks(), staleTime: 30_000 });

export const useCreateDesk = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { employee_id: string; enabled_widgets: string[] }) =>
      createWorkDesk(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
};

export const useUpdateDeskWidgets = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled_widgets }: { id: string; enabled_widgets: string[] }) =>
      updateWorkDeskWidgets(id, enabled_widgets),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
};

export const useRevokeDesk = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => revokeWorkDesk(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
};

export const useRegenerateDesk = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => regenerateWorkDesk(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
};
