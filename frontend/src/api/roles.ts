import { api } from './client';
import type { Role } from '../types/api';

export const getRoles = () => api.get<Role[]>('/roles');
export const createRole = (body: Partial<Role>) => api.post<Role>('/roles', body);
export const patchRole = (id: string, body: Partial<Role>) =>
  api.patch<Role>(`/roles/${id}`, body);
export const deleteRole = (id: string) => api.del<void>(`/roles/${id}`);
export const reorderRoles = (ids: string[]) =>
  api.post<void>('/roles/reorder', { ids });
