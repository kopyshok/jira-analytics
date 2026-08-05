import { api, boolParam } from './client';

export type FlagCode =
  | 'over' | 'under' | 'decomp' | 'childgap' | 'noest' | 'nospent' | 'stale';

export type StatusGroup = 'dev' | 'waiting' | 'todo' | 'done' | 'unassigned';

export interface ReviewedMark {
  flag: FlagCode;
  comment: string | null;
  marked_at: string;
}

export interface DeskIssue {
  id: string;
  key: string;
  summary: string;
  issue_type: string;
  status: string;
  status_group: StatusGroup;
  developer_id: string | null;
  developer_name: string | null;
  parent_id: string | null;
  est_hours: number | null;
  fact_hours: number;
  fact_by_person: { name: string; hours: number }[];
  days_in_status: number;
  is_analysis: boolean;
  is_subtask: boolean;
  flags: FlagCode[];
  signatures: Partial<Record<FlagCode, string>>;
  reviewed: ReviewedMark[];
}

export interface DeskDeveloper {
  developer_id: string;
  display_name: string | null;
  /** Команда человека; «добран точечно» — если выбран поверх команд. */
  team?: string | null;
  total_issues: number;
  in_dev: number;
  waiting: number;
  todo: number;
  est_hours: number;
  fact_hours: number;
  accuracy: number | null;
  flag_counts: Partial<Record<FlagCode, number>>;
}

export interface DeskWorkload {
  queue_hours: number;
  without_estimate: number;
  available_hours: number;
  queue_days: number | null;
  overloaded: boolean;
}

export interface DeskOverview {
  developers: DeskDeveloper[];
  issues: DeskIssue[];
  flag_counts: Partial<Record<FlagCode, number>>;
  workload: Record<string, DeskWorkload>;
  employee_ids: Record<string, string>;
}

export interface DeskSettings {
  status_groups: Record<string, string[]>;
  queue_statuses: string[];
  thresholds: Record<string, number>;
  subtask_types: string[];
  assignee_types: string[];
  /** Роли, попадающие в срез. По умолчанию только «Разработчик». */
  developer_roles: string[];
}

export interface DeskFilterPrefs {
  teams: string[];
  developers: string[];
}

/** Часы на экране — один знак после запятой: суммы списаний дают длинный хвост. */
export const roundHours = (value: number): number => Math.round(value * 10) / 10;

export const FLAG_LABELS: Record<FlagCode, string> = {
  over: 'Перерасход',
  under: 'Недорасход',
  decomp: 'Без декомпозиции',
  childgap: 'Подзадачи недооценены',
  noest: 'Нет оценки',
  nospent: 'Нет списаний',
  stale: 'Зависла',
};

export const FLAG_ORDER: FlagCode[] = [
  'over', 'under', 'decomp', 'childgap', 'noest', 'nospent', 'stale',
];

export const STATUS_GROUP_LABELS: Record<StatusGroup, string> = {
  dev: 'у разработчика',
  waiting: 'ждёт не его',
  todo: 'не начата',
  done: 'закрыта',
  unassigned: 'статус не распределён',
};

export const teamDeskApi = {
  overview: (params: {
    teams?: string;
    developers?: string;
    only_open?: boolean;
    show_reviewed?: boolean;
  }) =>
    api.get<DeskOverview>('/team-desk/overview', {
      teams: params.teams,
      developers: params.developers,
      only_open: boolParam(params.only_open),
      show_reviewed: boolParam(params.show_reviewed),
    }),

  settings: () => api.get<DeskSettings>('/team-desk/settings'),

  filter: () => api.get<DeskFilterPrefs>('/users/me/team-desk-filter'),

  saveFilter: (payload: DeskFilterPrefs) =>
    api.put<DeskFilterPrefs>('/users/me/team-desk-filter', payload),

  saveSettings: (payload: DeskSettings) =>
    api.put<DeskSettings>('/team-desk/settings', payload),

  mark: (issueId: string, payload: { flag: FlagCode; signature: string; comment?: string }) =>
    api.post<{ issue_id: string; flag: string; marked_at: string }>(
      `/team-desk/issues/${issueId}/mark`,
      payload,
    ),

  unmark: (issueId: string, flag: FlagCode) =>
    api.del<{ issue_id: string; flag: string }>(
      `/team-desk/issues/${issueId}/mark?flag=${flag}`,
    ),
};
