import { api } from './client';

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  role: 'admin' | 'super_manager' | 'manager';
  default_team: string | null;
  selected_teams: string[];
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return api.post<TokenResponse>('/auth/login', { email, password });
}

export function logout(): Promise<void> {
  return api.post<void>('/auth/logout');
}

export function getMe(): Promise<UserProfile> {
  return api.get<UserProfile>('/auth/me');
}

export function updateMyTeams(teams: string[]): Promise<UserProfile> {
  return api.put<UserProfile>('/auth/me/teams', { teams });
}
