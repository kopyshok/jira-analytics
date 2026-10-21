import { api } from './client';

export interface MergeCard {
  id: string;
  display_name: string;
  jira_username: string | null;
  email: string | null;
  is_active: boolean;
  role: string | null;
  teams: string[];
  worklogs: number;
  hours: number;
  first_worklog: string | null;
  last_worklog: string | null;
}

export interface MergeMove {
  label: string;
  count: number;
}

export interface MergePreview {
  keep: MergeCard;
  drop: MergeCard;
  moves: MergeMove[];
  blockers: string[];
}

export const employeeMergeApi = {
  suggestions: () => api.get<{ cards: MergeCard[] }[]>('/admin/employee-merge/suggestions'),
  preview: (keepId: string, dropId: string) =>
    api.get<MergePreview>('/admin/employee-merge/preview', { keep_id: keepId, drop_id: dropId }),
  merge: (keepId: string, dropId: string) =>
    api.post<{ keep: MergeCard; moves: MergeMove[] }>(
      '/admin/employee-merge', { keep_id: keepId, drop_id: dropId },
    ),
};
