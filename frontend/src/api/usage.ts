import { api } from './client';

export interface UsageOverview {
  dau: number;
  wau: number;
  mau: number;
  hours_30d: number;
}

export interface UsageUserRow {
  user_id: string;
  display_name: string;
  role: string;
  last_seen: string | null;
  active_days: number;
  hours: number;
  top_path: string | null;
}

export interface UsagePageRow {
  path: string;
  unique_users: number;
  views: number;
  hours: number;
}

export interface UsageMatrixCell {
  user_id: string;
  display_name: string;
  path: string;
  hours: number;
}

export interface UsageMatrix {
  users: { user_id: string; display_name: string }[];
  paths: { path: string }[];
  cells: UsageMatrixCell[];
}

export interface UsageTimelinePoint {
  date: string;
  views: number;
  seconds: number;
  active_users: number;
}

export interface UsageActionTopUser {
  user_id: string;
  display_name: string;
  count: number;
}

export interface UsageActionRow {
  action_type: string;
  total: number;
  top_users: UsageActionTopUser[];
}

export const usageApi = {
  overview: () => api.get<UsageOverview>('/admin/usage/overview'),
  users: (days: number) =>
    api.get<UsageUserRow[]>('/admin/usage/users', { days: String(days) }),
  pages: (days: number) =>
    api.get<UsagePageRow[]>('/admin/usage/pages', { days: String(days) }),
  matrix: (days: number) =>
    api.get<UsageMatrix>('/admin/usage/matrix', { days: String(days) }),
  timeline: (days: number) =>
    api.get<UsageTimelinePoint[]>('/admin/usage/timeline', { days: String(days) }),
  actions: (days: number) =>
    api.get<UsageActionRow[]>('/admin/usage/actions', { days: String(days) }),
};
