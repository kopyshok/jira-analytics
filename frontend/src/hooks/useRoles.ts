import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Role } from '../types/api';
import * as rolesApi from '../api/roles';

const KEY = ['roles'];

export function useRoles() {
  return useQuery<Role[]>({
    queryKey: KEY,
    queryFn: rolesApi.getRoles,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Role>) => rolesApi.createRole(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function usePatchRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<Role> }) =>
      rolesApi.patchRole(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => rolesApi.deleteRole(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useReorderRoles() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => rolesApi.reorderRoles(ids),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
