import { api, boolParam } from './client';

export type FlagCode =
  | 'over' | 'under' | 'decomp' | 'childgap' | 'orphan'
  | 'noest' | 'nospent' | 'idlespent' | 'stale';

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
  /** Задача идёт в счётчики и часы: не подзадача либо подзадача без родителя. */
  is_standalone: boolean;
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
  /** Разбивка задач по статусам; сумма равна total_issues. */
  status_counts: Record<string, number>;
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
  /** Статусы, которых раздел не показывает вовсе. */
  hidden_statuses: string[];
  thresholds: Record<string, number>;
  subtask_types: string[];
  assignee_types: string[];
  /** Роли, попадающие в срез. По умолчанию только «Разработчик». */
  developer_roles: string[];
}

/** Режим среза: открытые сейчас / окно периода / вся история. */
export type DeskMode = 'open' | 'period' | 'all';

/** Шапка раздела целиком — живёт в профиле, переживает выход из раздела. */
export interface DeskFilterPrefs {
  teams: string[];
  developers: string[];
  mode: DeskMode;
  period_start: string | null;
  period_end: string | null;
  show_reviewed: boolean;
  show_done_subtasks: boolean;
  /** Статусы, показываемые счётчиками. Пусто — все статусы среза. */
  status_counters: string[];
}

/** Часы на экране — один знак после запятой: суммы списаний дают длинный хвост. */
export const roundHours = (value: number): number => Math.round(value * 10) / 10;

export const FLAG_LABELS: Record<FlagCode, string> = {
  over: 'Перерасход',
  under: 'Недорасход',
  decomp: 'Без декомпозиции',
  childgap: 'Подзадачи недооценены',
  orphan: 'Подзадача без родителя',
  noest: 'Нет оценки',
  nospent: 'Нет списаний',
  idlespent: 'Часы в неначатой',
  stale: 'Зависла',
};

export const FLAG_ORDER: FlagCode[] = [
  'over', 'under', 'decomp', 'childgap', 'orphan',
  'noest', 'nospent', 'idlespent', 'stale',
];

export const FLAG_ICON: Record<FlagCode, string> = {
  over: '↑', under: '↓', decomp: '⊞', childgap: '⊟', orphan: '⚠',
  noest: '∅', nospent: '◔', idlespent: '⏱', stale: '⏳',
};

export const FLAG_COLOR: Record<FlagCode, string> = {
  over: 'red', under: 'gold', decomp: 'orange', childgap: 'volcano',
  orphan: 'magenta',
  noest: 'default', nospent: 'default', idlespent: 'geekblue', stale: 'purple',
};

export const STATUS_GROUP_LABELS: Record<StatusGroup, string> = {
  dev: 'у разработчика',
  waiting: 'ждёт не его',
  todo: 'не начата',
  done: 'закрыта',
  unassigned: 'статус не распределён',
};

export const STATUS_GROUP_COLOR: Record<StatusGroup, string> = {
  dev: '#4ba3ff',
  waiting: '#eeb13c',
  todo: '#788799',
  done: '#3ebd85',
  unassigned: '#a78bfa',
};

/** Порядок групп: сначала мяч у разработчика, в конце нераспределённые статусы. */
export const STATUS_GROUP_ORDER: StatusGroup[] = ['dev', 'waiting', 'todo', 'done', 'unassigned'];

export function statusGroupOf(
  statusGroups: Record<string, string[]> | undefined,
  status: string,
): StatusGroup {
  for (const group of STATUS_GROUP_ORDER) {
    if ((statusGroups?.[group] ?? []).includes(status)) return group;
  }
  return 'unassigned';
}

/**
 * Статусы в порядке групп — один и тот же порядок во всех раскладках.
 * Внутри группы сохраняется порядок из настроек раздела; статусы, не попавшие
 * ни в одну группу, идут в конце по алфавиту.
 */
export function orderedStatuses(
  statusGroups: Record<string, string[]> | undefined,
  seen: Iterable<string>,
): string[] {
  const rest = new Set(seen);
  const out: string[] = [];
  for (const group of STATUS_GROUP_ORDER) {
    for (const status of statusGroups?.[group] ?? []) {
      if (rest.delete(status)) out.push(status);
    }
  }
  return [...out, ...[...rest].sort((a, b) => a.localeCompare(b))];
}

export const teamDeskApi = {
  overview: (params: {
    teams?: string;
    developers?: string;
    only_open?: boolean;
    show_reviewed?: boolean;
    show_done_subtasks?: boolean;
    period_start?: string;
    period_end?: string;
  }) =>
    api.get<DeskOverview>('/team-desk/overview', {
      teams: params.teams,
      developers: params.developers,
      only_open: boolParam(params.only_open),
      show_reviewed: boolParam(params.show_reviewed),
      show_done_subtasks: boolParam(params.show_done_subtasks),
      period_start: params.period_start,
      period_end: params.period_end,
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
