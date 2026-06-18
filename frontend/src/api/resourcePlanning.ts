import { api } from './client';

export interface ScheduledBlock {
  id: string;
  team: string | null;
  role_ids: string[];
  employee_ids: string[];
  start_date: string;
  end_date: string;
  reason: string;
  created_at: string;
}

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
  off?: 'weekend' | 'holiday' | 'absence' | null;
}

export interface EmployeeLoadOut {
  employee_id: string;
  employee_name: string | null;
  employee_role: string | null;
  days: EmployeeLoadDay[];
}

export interface ResetCounts {
  pinned_dates: number;
  pinned_employees: number;
  edited_predecessors: number;
}

export interface GanttProjection {
  plan: ResourcePlan;
  assignments: AssignmentOut[];
  conflicts: ConflictOut[];
  pert_projection: InitiativePertOut[];
  dependencies: DependencyOut[];
  employee_load?: EmployeeLoadOut[];
  reset_counts: ResetCounts;
}

export interface AssignmentPatch {
  employee_id?: string | null;
  start_date?: string;
  end_date?: string;
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
  view_mode: string | null;
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

export const createScheduledBlock = (data: Omit<ScheduledBlock, 'id' | 'created_at'>) =>
  api.post<ScheduledBlock>('/resource-planning/scheduled-blocks', data);

export const updateScheduledBlock = (id: string, data: Partial<Omit<ScheduledBlock, 'id' | 'created_at'>>) =>
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
  status: 'work' | 'absence' | 'holiday' | 'weekend' | 'blocked_by_other' | 'pre_start_idle';
  blocker_assignment_id?: string | null;
  blocker_item_key?: string | null;
  blocker_phase_label?: string | null;
  absence_reason?: string | null;
  is_pre_start?: boolean;
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
