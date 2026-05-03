import { api } from './client';

export interface ScheduledBlock {
  id: string;
  team: string | null;
  role_id: string | null;
  employee_id: string | null;
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
  backlog_item_title: string;
  phase: 'analyst' | 'dev' | 'qa' | 'opo';
  employee_id: string | null;
  employee_name: string | null;
  part_number: number;
  hours_allocated: number | null;
  start_date: string | null;
  end_date: string | null;
  is_on_critical_path: boolean;
  slack_days: number | null;
}

export interface ConflictOut {
  id: string;
  type: string;
  severity: 'critical' | 'warning' | 'info';
  status: 'open' | 'acknowledged' | 'muted' | 'resolved';
  backlog_item_id: string | null;
  backlog_item_title: string | null;
  employee_id: string | null;
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

export interface GanttProjection {
  plan: ResourcePlan;
  assignments: AssignmentOut[];
  conflicts: ConflictOut[];
  pert_projection: InitiativePertOut[];
}

export interface AssignmentPatch {
  employee_id?: string | null;
  start_date?: string;
  end_date?: string;
  hours_allocated?: number;
}

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

export const getGanttProjection = (id: string) =>
  api.get<GanttProjection>(`/resource-planning/resource-plans/${id}/gantt`);

export const patchConflict = (planId: string, conflictId: string, status: ConflictOut['status']) =>
  api.patch<ConflictOut>(
    `/resource-planning/resource-plans/${planId}/conflicts/${conflictId}`,
    { status },
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
