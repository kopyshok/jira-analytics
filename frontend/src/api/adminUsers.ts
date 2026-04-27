import { api } from './client';
import type { UserProfile } from './auth';

export interface UserCreate {
  email: string;
  password: string;
  display_name: string;
  role: 'admin' | 'super_manager' | 'manager';
  default_team?: string | null;
}

export interface UserUpdate {
  display_name?: string;
  role?: 'admin' | 'super_manager' | 'manager';
  default_team?: string | null;
  is_active?: boolean;
}

export function listUsers(): Promise<UserProfile[]> {
  return api.get<UserProfile[]>('/admin/users/');
}

export function createUser(data: UserCreate): Promise<UserProfile> {
  return api.post<UserProfile>('/admin/users/', data);
}

export function updateUser(id: string, data: UserUpdate): Promise<UserProfile> {
  return api.put<UserProfile>(`/admin/users/${id}`, data);
}

export function resetPassword(id: string, newPassword: string): Promise<UserProfile> {
  return api.post<UserProfile>(`/admin/users/${id}/reset-password`, { new_password: newPassword });
}
