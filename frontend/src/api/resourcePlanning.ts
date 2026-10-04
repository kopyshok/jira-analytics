import { api } from './client';

export interface ScheduledBlock {
  id: string;
  team: string | null;
  role_ids: string[];
  employee_ids: string[];
  start_date: string;
  end_date: string;
  reason: string;
  work_type_id: string | null;
  /** Подпись вида работ; пусто — период создан до ввода вида работ. */
  work_type_label?: string | null;
  /** Подписи ролей периода. */
  role_labels?: string[];
  /** Имена сотрудников периода. */
  employee_names?: string[];
  /** Кого период не закрывает: в этом месяце у них период того же вида по роли или лично. */
  not_applied?: { employee_id: string; employee_name: string; month: string; by: 'role' | 'employee' }[];
  created_at: string;
}

export type ScheduledBlockInput = Omit<
  ScheduledBlock,
  'id' | 'created_at' | 'work_type_label' | 'role_labels' | 'employee_names' | 'not_applied'
> & { work_type_id: string };

export interface ResourcePlan {
  id: string;
  scenario_id: string | null;
  team: string | null;
  quarter: string | null;
  year: number | null;
  status: 'draft' | 'computing' | 'ready' | 'stale';
  computed_at: string | null;
  created_at: string;
  parent_plan_id: string | null;
  is_baseline: boolean;
  label: string | null;
}

export interface AssignmentShift {
  backlog_item_id: string;
  backlog_item_title?: string | null;
  phase: string;
  part_number: number;
  kind: 'added' | 'removed' | 'shifted';
  start_delta_days?: number;
  end_delta_days?: number;
  employee_changed?: boolean;
}

export interface PlanDiffMetrics {
  assignments_count: number;
  critical_path_count: number;
  last_end_date: string | null;
  conflicts_open: number;
  conflicts_critical: number;
}

export interface PlanDiff {
  baseline_id: string;
  scenario_id: string;
  assignment_shifts: AssignmentShift[];
  baseline_metrics: PlanDiffMetrics;
  scenario_metrics: PlanDiffMetrics;
}

export interface AssignmentOut {
  id: string;
  backlog_item_id: string;
  backlog_item_key: string | null;
  backlog_item_title: string;
  phase: 'analyst' | 'dev' | 'qa' | 'opo';
  employee_id: string | null;
  employee_name: string | null;
  employee_role: string | null;
  part_number: number;
  /** Часть ОПЭ строки; null — у прочих фаз и старых строк (тогда — по роли). */
  opo_part?: 'analyst' | 'dev' | null;
  hours_allocated: number | null;
  start_date: string | null;
  end_date: string | null;
  is_on_critical_path: boolean;
  slack_days: number | null;
  is_pinned: boolean;
  pinned_employee?: boolean;
  pinned_start?: boolean;
  pinned_split?: boolean;
  manual_edit_at?: string | null;
  predecessor_ids?: string[];
  unavailable_days?: Array<{ date: string; type: 'weekend' | 'holiday' | 'absence' | 'block' }>;
  scenario_assignee_employee_id?: string | null;
  scenario_assignee_name?: string | null;
  /** Приоритет инициативы. Чем выше число — тем выше приоритет. */
  priority?: number | null;
  /** Авто-сплит выключен; поля оставлены для обратной совместимости. */
  chunk_index?: number | null;
  chunks_total?: number | null;
  out_of_quarter: boolean;
  daily_hours: Record<string, number> | null;
  worklog_hours_actual: number;
  /** Группа внутри команды, к которой отнесена работа. */
  subgroup_id?: string | null;
  /** Работа на группу, где у исполнителя нет доли во все дни назначения — помощь соседней группе. */
  other_subgroup?: boolean;
  /** Даты, когда работа идёт на соседнюю группу (перевод посреди назначения — с даты перевода). */
  other_subgroup_ranges?: { start: string; end: string }[];
}

export interface ConflictOut {
  id: string;
  type: string;
  severity: 'critical' | 'warning' | 'info';
  status: 'open' | 'acknowledged' | 'muted' | 'resolved';
  backlog_item_id: string | null;
  backlog_item_title: string | null;
  employee_id: string | null;
  employee_name?: string | null;
  assignment_id: string | null;
  window_start: string | null;
  window_end: string | null;
  metric_value: number | null;
  message: string;
  created_at: string;
  updated_at: string;
  /** «Живой» конфликт (пересечение с другой командой): не хранится, статус не меняется. */
  is_live?: boolean;
}

export interface InitiativePertOut {
  backlog_item_id: string;
  backlog_item_title: string;
  most_likely_finish: string | null;
  p50_finish: string | null;
  p90_finish: string | null;
  sigma_days: number;
  on_critical_path_only: boolean;
}

export interface DependencyOut {
  id: string;
  plan_id: string;
  from_item_id: string;
  to_item_id: string;
  dep_type: 'FS' | 'SS' | 'FF' | 'SF';
  lag_days: number;
  source: 'manual' | 'inferred';
}

export interface UnavailableDay {
  date: string;
  type: 'weekend' | 'holiday' | 'absence' | 'block';
}

export interface EmployeeLoadDay {
  date: string;
  pct: number;
  /** Нерабочий день: 'weekend' | 'holiday' | 'absence'. Отсутствует — рабочий. */
  off?: 'weekend' | 'holiday' | 'absence' | 'out_of_team' | null;
  /** Доля ёмкости дня, занятая планами других команд, %. */
  ext_pct?: number;
  /** Нормированные работы дня: заблокированный период, остаток дня после
   *  вовлечённости и доля запаса на свободное время. Доля ёмкости дня, %. */
  normed_pct?: number;
  /** То же в часах. */
  normed_hours?: number;
  /** Заблокированный день: «причина · вид работ». */
  blocked?: string | null;
}

/** Часы нормированных работ по виду — для подсказки у имени и сводки. */
export interface NormedTypeHours {
  label: string;
  hours: number;
}

/** За счёт какого запаса основной команды идут часы человека в других командах:
 *  вид работ и его запас на роль человека (как в сводке запаса). */
export interface ReserveUseOut {
  team: string;
  work_type_id: string;
  label: string;
  /** Часы этого человека в других командах, списанные на этот вид. */
  hours: number;
  planned_hours: number;
  used_hours: number;
  remaining_hours: number;
  overuse_hours: number;
}

/** Загрузка человека за квартал, часы; одинакова в плане любой команды. */
export interface EmployeeQuarterLoad {
  capacity_hours: number;
  own_hours: number;
  other_teams_hours: number;
  normed_hours: number;
  unplaced_hours: number;
  pct: number;
  normed_by_type: NormedTypeHours[];
  /** Работа в других командах по видам запаса основной команды. */
  reserve_use?: ReserveUseOut[];
  /** Задача другой команды → вид работ, за счёт которого она идёт. */
  reserve_items?: Record<string, string>;
}

/** Переход сотрудника на границе участия в команде плана внутри квартала. */
export interface TeamMove {
  /** Выбыл — первый день вне команды; пришёл — первый день в команде. */
  date: string;
  /** Команда по ту сторону границы; null — ни в одной команде. */
  team: string | null;
}

export interface EmployeeLoadOut {
  employee_id: string;
  employee_name: string | null;
  employee_role: string | null;
  days: EmployeeLoadDay[];
  /** Первый день участия в команде внутри квартала; null — участие с начала квартала. */
  member_from?: string | null;
  /** Последний день участия внутри квартала; null — участие до конца квартала. */
  member_to?: string | null;
  /** Куда выбыл внутри квартала; null — участие до конца квартала. */
  left_to?: TeamMove | null;
  /** Откуда пришёл внутри квартала; null — участие с начала квартала. */
  joined_from?: TeamMove | null;
  /** Привлечён из другой команды (в команде плана не состоял ни дня квартала). */
  is_borrowed?: boolean;
  borrowed_from?: string | null;
  /** Загрузка за квартал: запас нормированных работ основной команды человека. */
  quarter?: EmployeeQuarterLoad | null;
}

/** Свободные часы наблюдаемого в месяце квартала. */
export interface WatchMonthFree {
  /** Первое число месяца, YYYY-MM-DD. */
  month: string;
  hours: number;
}

/** Наблюдаемый: строка «Загрузки по дням» той же формулой, что у людей плана.
 *  Свой слой — задачи его основной команды (и этого плана), другие команды — остальное. */
export interface WatchRowOut extends EmployeeLoadOut {
  home_team: string | null;
  /** Свободно за квартал: норма − задачи − нормированные работы, ч. */
  free_hours: number;
  free_by_month: WatchMonthFree[];
  /** «Технические задачи» роли человека в запасе основной команды (общий на роль). */
  tech_reserve: ReserveTypeRow | null;
  /** Занят в этом плане. */
  in_plan: boolean;
}

export interface PlanWatchOut {
  rows: WatchRowOut[];
  /** Брони наблюдаемых в опорных планах других команд — для подсказки дня. */
  bookings: ExternalBookingOut[];
}

export interface ResetCounts {
  pinned_dates: number;
  pinned_employees: number;
  edited_predecessors: number;
}

/** Фаза человека из этого плана в опорном плане другой команды. */
export interface ExternalBookingOut {
  assignment_id: string;
  employee_id: string;
  employee_name: string | null;
  team: string;
  /** Задача брони — по ней подсказка дня находит вид работ запаса. */
  backlog_item_id?: string | null;
  issue_key: string | null;
  title: string;
  phase: string;
  start: string;
  end: string;
  /** {"YYYY-MM-DD": часы} внутри окна диаграммы (квартал + месяц запаса). */
  daily_hours: Record<string, number>;
  /** Опорный план — черновик сценария (утверждённого у команды нет). */
  provisional: boolean;
  /** Человек привлечён в ЭТОТ план (в его команде не состоял ни дня квартала). */
  employee_is_borrowed: boolean;
  /** Бронь-привлечение: команда брони человеку не домашняя (не состоит в ней
   *  или она у него не основная) — она подстраивается и получает конфликт. */
  is_borrowing: boolean;
  /** Дни брони, где этот план тоже занял человека и вместе выходит больше его дня. */
  overlap_days: string[];
}

/** Запас вида работ роли и его расход с датой, часы. */
export interface ReserveTypeRow {
  work_type_id: string;
  label: string;
  planned_hours: number;
  blocked_hours: number;
  other_teams_hours: number;
  remaining_hours: number;
  overuse_hours: number;
}

export interface ReserveRoleOut {
  role: string;
  role_label: string;
  rows: ReserveTypeRow[];
}

/** Работа людей команды плана над задачей другой команды за квартал. */
export interface OtherTeamWorkOut {
  backlog_item_id: string;
  issue_key: string | null;
  title: string;
  team: string;
  /** Роль исполнителя — как у ReserveRoleOut.role; строка раскрывается в таблице этой роли. */
  role: string;
  hours: number;
  work_type_id: string;
  is_manual: boolean;
}

export interface WorkTypeOption {
  id: string;
  label: string;
}

/** Запас нормированных работ команды плана на квартал. */
export interface ReserveOut {
  team: string;
  scenario_name: string;
  roles: ReserveRoleOut[];
  other_team_work: OtherTeamWorkOut[];
  work_types: WorkTypeOption[];
}

export interface GanttProjection {
  plan: ResourcePlan;
  assignments: AssignmentOut[];
  conflicts: ConflictOut[];
  pert_projection: InitiativePertOut[];
  dependencies: DependencyOut[];
  employee_load?: EmployeeLoadOut[];
  /** Сотрудник команды плана → группы, где у него есть доля в дни участия
   *  внутри квартала плана, по убыванию «доля × дни» (первая — главная).
   *  Команда без деления — пусто. */
  employee_subgroups?: Record<string, string[]>;
  /** Брони людей плана (свои и привлечённые) в опорных планах других команд. */
  external_bookings?: ExternalBookingOut[];
  /** Брони, вычитаемые из доступности плана, изменились после его расчёта. */
  stale_due_to_other_teams?: boolean;
  /** Команды, чьи планы изменились после расчёта. */
  stale_teams?: string[];
  /** Запас нормированных работ команды плана на квартал; null — запаса нет. */
  reserve?: ReserveOut | null;
  reset_counts: ResetCounts;
}

export interface AssignmentPatch {
  employee_id?: string | null;
  start_date?: string;
  hours_allocated?: number;
  predecessor_ids?: string[];
  /** Явное закрепление даты. Опускаем → drag по дате ставит флаг как раньше. */
  pinned_start?: boolean;
  /** Подтверждение смены сотрудника при наличии конфликтов (отпуска/перегрузки). */
  force?: boolean;
}

export interface EmployeeAbsenceConflict {
  start_date: string;
  end_date: string;
  reason: string | null;
  overlap_days: number;
}

export interface EmployeeOverloadConflict {
  date: string;
  other_assignment_id: string;
  other_phase: string;
  other_backlog_item_key: string | null;
  other_backlog_item_title: string;
  hours_on_day: number;
}

export interface EmployeeChangePreviewResponse {
  new_employee_id: string;
  new_employee_name: string | null;
  absences: EmployeeAbsenceConflict[];
  overloads: EmployeeOverloadConflict[];
  has_conflicts: boolean;
}

export interface RpPreferences {
  hide_weekends: boolean;
  collapsed_initiative_ids: string[];
  /** Вид страницы: 'tasks' — по задачам (null — тоже), 'people' — по исполнителям. */
  view_mode: 'tasks' | 'people' | null;
  show_relay: boolean;
  detail_sections_visible: Record<string, boolean>;
  detail_sections_collapsed: Record<string, boolean>;
  fill_intensity_pct: number;
  fill_contrast_pct: number;
  pulse_highlighted_employee: boolean;
  pulse_critical_path: boolean;
  out_of_quarter_months: number;
  hide_weekend_stripes_week_mode: boolean;
}

export const getRpPreferences = () =>
  api.get<RpPreferences>('/resource-planning/preferences');

export const patchRpPreferences = (data: Partial<RpPreferences>) =>
  api.patch<RpPreferences>('/resource-planning/preferences', data);

export interface SplitRequest {
  parts: number[];
  cascade?: boolean;
}

export interface AssignmentDto {
  id: string;
  plan_id: string;
  backlog_item_id: string;
  phase: string;
  employee_id: string | null;
  part_number: number;
  hours_allocated: number | null;
  start_date: string | null;
  end_date: string | null;
  pinned_employee: boolean;
  pinned_start: boolean;
  pinned_split: boolean;
  is_pinned: boolean;
  manual_edit_at: string | null;
}

export const splitAssignment = (
  planId: string,
  assignmentId: string,
  data: SplitRequest,
) =>
  api.post<{ parts: AssignmentDto[]; cascaded: AssignmentDto[] }>(
    `/resource-planning/resource-plans/${planId}/assignments/${assignmentId}/split`,
    data,
  );

export const mergeAssignment = (planId: string, assignmentId: string) =>
  api.post<{ assignment: AssignmentDto }>(
    `/resource-planning/resource-plans/${planId}/assignments/${assignmentId}/merge`,
    {},
  );

export type ManualEditFlag = 'start' | 'employee' | 'split';

export const clearAssignmentManualEdit = (
  planId: string,
  assignmentId: string,
  flags?: ManualEditFlag[],
) => {
  const query = flags && flags.length ? `?flags=${flags.join(',')}` : '';
  return api.del(
    `/resource-planning/resource-plans/${planId}/assignments/${assignmentId}/manual-edit${query}`,
  );
};

export const getScheduledBlocks = (team?: string) =>
  api.get<ScheduledBlock[]>('/resource-planning/scheduled-blocks', team ? { team } : undefined);

export const createScheduledBlock = (data: ScheduledBlockInput) =>
  api.post<ScheduledBlock>('/resource-planning/scheduled-blocks', data);

export const updateScheduledBlock = (id: string, data: Partial<ScheduledBlockInput>) =>
  api.patch<ScheduledBlock>(`/resource-planning/scheduled-blocks/${id}`, data);

export const deleteScheduledBlock = (id: string) =>
  api.del(`/resource-planning/scheduled-blocks/${id}`);

export const getResourcePlans = (team?: string) =>
  api.get<ResourcePlan[]>('/resource-planning/resource-plans', team ? { team } : undefined);

export const createResourcePlan = (data: { scenario_id?: string; team: string; quarter: string; year: number }) =>
  api.post<ResourcePlan>('/resource-planning/resource-plans', data);

export const deleteResourcePlan = (id: string) =>
  api.del(`/resource-planning/resource-plans/${id}`);

export const computeResourcePlan = (id: string) =>
  api.post<ResourcePlan>(`/resource-planning/resource-plans/${id}/compute`, {});

export type BulkClearMode = 'dates' | 'employees' | 'predecessors' | 'all';

export interface BulkClearResponse {
  cleared_count: number;
  mode: BulkClearMode;
}

export const bulkClearAssignments = (planId: string, mode: BulkClearMode) =>
  api.post<BulkClearResponse>(
    `/resource-planning/resource-plans/${planId}/bulk-clear`,
    { mode },
  );

export const getGanttProjection = (id: string) =>
  api.get<GanttProjection>(`/resource-planning/resource-plans/${id}/gantt`);

export const patchConflict = (planId: string, conflictId: string, status: ConflictOut['status']) =>
  api.patch<ConflictOut>(
    `/resource-planning/resource-plans/${planId}/conflicts/${conflictId}`,
    { status },
  );

export interface ConflictExplainContributor {
  assignment_id: string;
  backlog_item_id: string;
  item_key: string | null;
  item_title: string;
  phase: 'analyst' | 'dev' | 'qa' | 'opo';
  phase_label: string;
  hours_per_day: number;
  hours_total: number;
  start_date: string;
  end_date: string;
  working_days: number;
}

export interface ConflictExplainOut {
  id: string;
  type: string;
  severity: ConflictOut['severity'];
  message: string;
  date: string | null;
  employee_id: string | null;
  employee_name: string | null;
  available_hours: number | null;
  demand_hours: number | null;
  overload_pct: number | null;
  contributors: ConflictExplainContributor[];
}

export const explainConflict = (planId: string, conflictId: string) =>
  api.get<ConflictExplainOut>(
    `/resource-planning/resource-plans/${planId}/conflicts/${conflictId}/explain`,
  );

export interface AssignmentExplainConflict {
  id: string;
  type: string;
  severity: ConflictOut['severity'];
  message: string;
  date: string | null;
  available_hours: number | null;
  demand_hours: number | null;
  overload_pct: number | null;
  contributors: ConflictExplainContributor[];
}

export interface DailyBreakdownItem {
  date: string;
  available_hours: number;
  used_hours: number;
  status: 'work' | 'absence' | 'holiday' | 'weekend' | 'blocked_by_other' | 'blocked' | 'pre_start_idle';
  blocker_assignment_id?: string | null;
  blocker_item_key?: string | null;
  blocker_phase_label?: string | null;
  absence_reason?: string | null;
  /** Причина заблокированного периода (status === 'blocked'). */
  block_reason?: string | null;
  is_pre_start?: boolean;
  co_occupants?: DayCoOccupant[];
}

export interface DayCoOccupant {
  item_key?: string | null;
  phase_label: string;
  hours: number;
}

export interface AbsenceWindowItem {
  date_start: string;
  date_end: string;
  reason_label: string;
  is_holiday: boolean;
}

export interface PhaseCalcDetails {
  duration_days_jira: number | null;
  involvement_pct: number | null;
  /** 'employee' — личная настройка сотрудника, 'task' — значение задачи, 'team' — из справочника команды. */
  involvement_source?: 'employee' | 'task' | 'team' | null;
  parallel_count: number;
  role_pct: number | null;
  daily_capacity_hours: number;
}

export interface HoursSummary {
  total: number;
  used: number;
  remaining: number;
  workdays: number;
  blocked_days: number;
}

/** @deprecated Используй AssignmentExplainResponseV2 */
export interface AssignmentExplainOut {
  assignment: {
    assignment_id: string;
    phase: 'analyst' | 'dev' | 'qa' | 'opo';
    employee_id: string | null;
    employee_name: string | null;
    start_date: string | null;
    end_date: string | null;
    hours_allocated: number | null;
    is_on_critical_path: boolean;
    slack_days: number | null;
  };
  conflicts: AssignmentExplainConflict[];
}

export interface AssignmentExplainResponseV2 {
  assignment: AssignmentOut;
  conflicts: AssignmentExplainConflict[];
  algorithm_log: string[];
  daily_breakdown: DailyBreakdownItem[];
  absences_in_window: AbsenceWindowItem[];
  phase_calc: PhaseCalcDetails | null;
  hours_summary: HoursSummary | null;
  /** @deprecated legacy back-compat (будет удалён в Task 14) */
  summary?: unknown;
}

export const explainAssignment = (planId: string, assignmentId: string) =>
  api.get<AssignmentExplainResponseV2>(
    `/resource-planning/resource-plans/${planId}/assignments/${assignmentId}/explain`,
  );

export const forkPlan = (planId: string, label?: string) =>
  api.post<ResourcePlan>(`/resource-planning/resource-plans/${planId}/fork`, { label });

export const getPlanDiff = (scenarioId: string, baselineId: string) =>
  api.get<PlanDiff>(`/resource-planning/resource-plans/${scenarioId}/diff/${baselineId}`);

export async function patchAssignment(
  planId: string,
  assignmentId: string,
  data: AssignmentPatch,
): Promise<AssignmentOut> {
  return api.patch<AssignmentOut>(
    `/resource-planning/resource-plans/${planId}/assignments/${assignmentId}`,
    data,
  );
}

/** Зафиксировать вовлечённость фазы (0..100%) у инициативы; null — снять фиксацию.
 *  Сервер пересчитывает план. */
export async function setAssignmentInvolvement(
  planId: string,
  assignmentId: string,
  involvementPct: number | null,
): Promise<void> {
  await api.put(
    `/resource-planning/resource-plans/${planId}/assignments/${assignmentId}/involvement`,
    { involvement_pct: involvementPct },
  );
}

export async function previewEmployeeChange(
  planId: string,
  assignmentId: string,
  employeeId: string,
): Promise<EmployeeChangePreviewResponse> {
  return api.post<EmployeeChangePreviewResponse>(
    `/resource-planning/resource-plans/${planId}/assignments/${assignmentId}/preview-employee-change`,
    { employee_id: employeeId },
  );
}

/** Кандидат в исполнители фазы. */
export interface AssignmentCandidate {
  employee_id: string;
  display_name: string;
  role: string | null;
  team: string | null;
  /** Загрузка за квартал плана по опорным планам всех команд, %; у кандидата
   *  фазы — с нормированными работами основной команды. */
  load_pct: number;
  /** Границы участия в команде плана внутри квартала; null — край покрыт. */
  member_from?: string | null;
  member_to?: string | null;
  /** Свободно в даты фазы, ч (только у кандидатов фазы плана). */
  free_hours?: number | null;
}

export interface AssignmentCandidateGroup {
  key: 'jira' | 'team' | 'other';
  label: string;
  employees: AssignmentCandidate[];
}

/** Все активные сотрудники группами «Из Jira» / «Моя команда» / «Другие команды». */
export const getAssignmentCandidates = (planId: string, assignmentId: string) =>
  api.get<AssignmentCandidateGroup[]>(
    `/resource-planning/resource-plans/${planId}/assignments/${assignmentId}/candidates`,
  );

export interface QualityMetric {
  plan_id: string;
  overload_days_pct: number;
  late_count: number;
  mean_utilization_pct: number;
  computed_at: string;
}

export const getPlanQuality = (planId: string, signal?: AbortSignal) =>
  api.get<QualityMetric>(`/resource-planning/resource-plans/${planId}/quality`, undefined, signal);

export const createDependency = (
  planId: string,
  data: { from_item_id: string; to_item_id: string; dep_type?: DependencyOut['dep_type']; lag_days?: number },
) =>
  api.post<DependencyOut>(`/resource-planning/resource-plans/${planId}/dependencies`, data);

export const patchDependency = (
  planId: string,
  depId: string,
  data: { dep_type?: DependencyOut['dep_type']; lag_days?: number },
) =>
  api.patch<DependencyOut>(`/resource-planning/resource-plans/${planId}/dependencies/${depId}`, data);

export const deleteDependency = (planId: string, depId: string) =>
  api.del(`/resource-planning/resource-plans/${planId}/dependencies/${depId}`);

export interface WorkTypeOverrideInput {
  team: string;
  backlog_item_id: string;
  /** null — вернуть вид по умолчанию («Технические задачи»). */
  work_type_id: string | null;
}

/** Чем команда считает работу своих людей над задачей другой команды. */
export const putWorkTypeOverride = (data: WorkTypeOverrideInput) =>
  api.put('/resource-planning/work-type-overrides', data);

/** Список наблюдения плана: «Наблюдаемые» в «Загрузке по дням». */
export const getPlanWatch = (planId: string) =>
  api.get<PlanWatchOut>(`/resource-planning/resource-plans/${planId}/watch`);

export const addPlanWatch = (planId: string, employeeIds: string[]) =>
  api.post(`/resource-planning/resource-plans/${planId}/watch`, { employee_ids: employeeIds });

export const removePlanWatch = (planId: string, employeeId: string) =>
  api.del(`/resource-planning/resource-plans/${planId}/watch/${employeeId}`);
