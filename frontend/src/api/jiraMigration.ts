import { api } from './client';

export type JobKind = 'dry_run' | 'apply' | 'full_sync';
export type JobState = 'idle' | 'running' | 'done' | 'error';
export type PersonStatus = 'by_hours' | 'by_name' | 'disputed' | 'not_found' | 'search_failed';
export type PersonSource = 'auto' | 'decision' | 'none' | 'conflict';
export type IssueAction = 'delete' | 'keep';

export interface MigrationJob {
  kind: JobKind | null;
  state: JobState;
  step: string | null;
  counters: Record<string, number>;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface ProbeItem {
  code: string;
  title: string;
  essential: boolean;
  ok: boolean;
  detail: string;
}

export interface DcField {
  id: string;
  name: string;
  custom: boolean;
}

export interface FieldDecision {
  dc_field_id: string | null;
}

export interface FieldRow {
  cloud_id: string;
  cloud_name: string;
  labels: string[];
  suggested_id: string | null;
  suggested_name: string | null;
  decision: FieldDecision | null;
  final_id: string | null;
  final_name: string | null;
  auto_only: boolean;
  unresolved: boolean;
}

export interface DcUserRef {
  key: string;
  name: string | null;
  display_name: string;
}

export interface PersonCandidate extends DcUserRef {
  votes: number;
}

export type PersonDecision =
  | { action: 'bind'; key: string; name: string | null; display_name: string }
  | { action: 'unbind' };

export interface PersonFinal {
  key: string | null;
  name: string | null;
  display_name: string | null;
  source: PersonSource;
  unresolved: boolean;
  note: string | null;
}

export interface PersonRow {
  employee_id: string;
  display_name: string;
  worklogs: number;
  matched: number;
  status: PersonStatus;
  candidates: PersonCandidate[];
  auto: DcUserRef | null;
  decision: PersonDecision | null;
  final: PersonFinal | null;
  /** Часы списаний на задачах, которые получат номера новой Jira (в старых отчётах нет). */
  hours_at_risk?: number;
}

export interface MissingIssue {
  key: string;
  summary: string;
  reasons: string[];
  decision: { action: IssueAction } | null;
}

export interface ProjectNotFound {
  key: string;
  issues: number;
}

export interface IssuesSummary {
  db_total: number;
  matched: number;
  new_in_dc: number;
  missing_total: number;
  deletable_total: number;
  deletable_sample: string[];
  /** Удалит применение: исчезнувшие без данных сервиса и с решением «удалить». */
  to_delete_total: number;
  /** Часы списаний на удаляемых задачах. */
  to_delete_hours: number;
  missing_with_data: MissingIssue[];
  project_not_found: ProjectNotFound[];
}

export interface HoursRow {
  team: string;
  month: string;
  db_hours: number;
  dc_hours: number;
  diff_pct: number;
  flagged: boolean;
}

export interface HoursSummary {
  rows: HoursRow[];
  db_worklogs: number;
  dc_worklogs: number;
  dc_worklogs_total: number;
}

export interface MigrationReport {
  status: 'running' | 'done' | 'failed';
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  age_hours: number | null;
  probe: ProbeItem[];
  // Только у успешного отчёта.
  dc_fields?: DcField[];
  projects?: { key: string; found: boolean }[];
  hours?: HoursSummary;
  offset_hours?: number | null;
  offset_matches?: number | null;
  offset_sample?: number | null;
  offset_unexpected?: boolean;
  // Только до применения и пока не идёт применение.
  fields?: FieldRow[];
  issues?: IssuesSummary;
  people?: PersonRow[];
  choices_dropped?: number;
}

export interface PostCheck {
  checked_at: string;
  db_worklogs: number;
  dc_worklogs: number;
  rows: HoursRow[];
}

export interface SyncRunBrief {
  id: string;
  /** Среди значений бывает «interrupted» — запуск прерван перезапуском сервиса. */
  status: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

/** Итог применения; набор чисел зависит от версии, поэтому все поля необязательные. */
export interface ApplySummary {
  settings?: number;
  projects?: number;
  issues_deleted?: number;
  issues_rebound?: number;
  plan_sources?: number;
  choices_dropped?: number;
  employees_bound?: number;
  employees_unbound?: number;
  /** Сколько ссылок на людей переписано — по местам хранения. */
  people_refs?: number | Record<string, number>;
  kpi_payload_skipped?: number;
  worklogs_deleted?: number;
  worklogs_kept?: number;
  comments_deleted?: number;
  comments_kept?: number;
  [key: string]: unknown;
}

export interface MigrationOverview {
  migration_state: 'pending' | 'done';
  job: MigrationJob;
  report: MigrationReport | null;
  unresolved: { fields: number; issues: number; people: number };
  blockers: string[];
  backup_command: string;
  applied_at: string | null;
  apply_summary: ApplySummary | null;
  sync_run: SyncRunBrief | null;
  post_check: PostCheck | null;
}

export interface DcUserOut {
  key: string;
  name: string | null;
  display_name: string;
  email: string | null;
  active: boolean;
}

export type DecisionBody =
  | { kind: 'field'; item_key: string; decision: FieldDecision | null }
  | { kind: 'issue'; item_key: string; decision: { action: IssueAction } | null }
  | { kind: 'person'; item_key: string; decision: PersonDecision | null };

const BASE = '/admin/jira-migration';

export const jiraMigrationApi = {
  overview: () => api.get<MigrationOverview>(BASE),
  startDryRun: () => api.post<MigrationJob>(`${BASE}/dry-run`, {}),
  setDecision: (body: DecisionBody) => api.put<{ ok: boolean }>(`${BASE}/decisions`, body),
  searchUsers: (q: string) => api.get<DcUserOut[]>(`${BASE}/dc-users`, { q }),
  apply: (backupConfirmed: boolean) =>
    api.post<MigrationJob>(`${BASE}/apply`, { backup_confirmed: backupConfirmed }),
  restartFullSync: () => api.post<MigrationJob>(`${BASE}/full-sync`, {}),
  postCheck: () => api.post<PostCheck>(`${BASE}/post-check`, {}),
};
