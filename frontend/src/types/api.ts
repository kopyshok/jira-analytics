// === Employees & Projects ===

export interface EmployeeTeamItem {
  team: string;
  is_primary: boolean;
}

export type EmployeeRole = string;  // now driven by roles registry

export interface Role {
  id: string;
  code: string;
  label: string;
  color: string;
  is_active: boolean;
  counts_in_planning: boolean;
  sort_order: number;
}

export interface EmployeeResponse {
  id: string;
  jira_account_id: string;
  display_name: string;
  email: string | null;
  avatar_url: string | null;
  is_active: boolean;
  role: EmployeeRole | null;
  team: string | null;  // legacy: имя primary team
  teams?: EmployeeTeamItem[];  // присутствует только если запросили with_teams=true
}

export interface JiraUserSearchResult {
  jira_account_id: string;
  display_name: string;
  email: string | null;
  is_active: boolean;
  avatar_url: string | null;
}

export interface EmployeeFromJiraRequest {
  jira_account_id: string;
  display_name: string;
  email: string | null;
  is_active: boolean;
  avatar_url: string | null;
}

export interface RecalcActiveResponse {
  activated: number;
  deactivated: number;
  total_active: number;
}

export interface ProjectResponse {
  id: string;
  key: string;
  name: string;
  is_active: boolean;
}

// === Categories ===

export interface CategoryResponse {
  id: string;
  code: string;
  label: string;
  color: string | null;
  sort_order: number;
  is_system: boolean;
  work_type_id: string | null;
}

// === Settings ===

export interface JiraSettingsResponse {
  email: string | null;
  base_url: string | null;
  has_token: boolean;
}

export interface JiraTestResponse {
  connected: boolean;
  user_name: string | null;
  user_email: string | null;
  error: string | null;
}

// === Sync ===

export interface ConnectionTestResponse {
  connected: boolean;
  user_name: string | null;
  user_email: string | null;
  error: string | null;
}

export interface SyncResponse {
  status: string;
  message: string;
  stats: Record<string, unknown> | null;
}

export interface SyncStatusResponse {
  entity: string;
  scope: string;
  last_sync: string | null;
  cursor: string | null;
  last_error: string | null;
}

export interface WorklogReloadRequest {
  since: string;   // YYYY-MM-DD
}

export interface WorklogReloadResponse {
  deleted: number;
  issues_scanned: number;
  worklogs_inserted: number;
}

// === Jira Browse ===

export interface JiraProjectItem {
  id: string;
  key: string;
  name: string;
  project_type: string | null;
  in_scope: boolean;
}

export interface JiraEpicItem {
  key: string;
  summary: string;
  issue_type: string;
  status: string;
}

// === Issue Tree ===

export interface IssueTreeNode {
  id: string;
  key: string;
  summary: string;
  issue_type: string;
  status: string;
  status_category: string | null;
  project_key: string;
  parent_key: string | null;
  assigned_category: string | null;
  category: string | null;
  include_in_analysis: boolean;
  status_changed_at: string | null;
  goals: string | null;
  is_context: boolean;
  is_container: boolean;
  category_verified: boolean;
  require_child_verification: boolean;
  children: IssueTreeNode[];
}

export interface IssueTreeRootNode {
  id: string;
  key: string;
  summary: string;
  issue_type: string;
  status: string;
  status_category: string | null;
  project_key: string;
  parent_key: string | null;
  assigned_category: string | null;
  category: string | null;
  include_in_analysis: boolean;
  status_changed_at: string | null;
  goals: string | null;
  is_context: boolean;
  is_container: boolean;
  category_verified: boolean;
  require_child_verification: boolean;
  has_children: boolean;
  descendant_count: number;
  descendant_match_count: number;
}

export interface IssueTreeCounts {
  stack: number;
  active: number;
  initiatives: number;
  archive_target: number;
  archive: number;
}

export interface EpicCandidateApi {
  id: string;
  key: string;
  summary: string;
  assigned_category: string;
}

// === Jira Fields ===

export interface JiraFieldItem {
  id: string;
  name: string;
  custom: boolean;
}

// === Scope ===

export interface ScopeProjectResponse {
  id: string;
  jira_project_key: string;
  jira_project_id: string | null;
  is_enabled: boolean;
}

export interface ScopeProjectBatchResponse {
  added: number;
  removed: number;
}

export interface ScopeRootResponse {
  id: string;
  category_code: string;
  jira_issue_key: string;
  jira_issue_id: string | null;
  project_key: string | null;
  is_enabled: boolean;
}

export interface CategoryOverrideResponse {
  id: string;
  jira_issue_key: string;
  category_code: string;
  comment: string | null;
}

// === Analytics ===

export interface AggregateRowResponse {
  key: string;
  label: string;
  total_hours: number;
  worklog_count: number;
}

export interface ContextSwitchRowResponse {
  employee_id: string;
  employee_name: string;
  total_worklogs: number;
  distinct_projects: number;
  distinct_categories: number;
  switches: number;
}

// === Mapping ===

export interface MappingResponse {
  status: string;
  message: string;
  stats: Record<string, unknown>;
}

// === Capacity ===

export interface AbsenceReason {
  id: string;
  code: string;
  label: string;
  is_planned: boolean;
  color: string | null;
  is_active: boolean;
  sort_order: number;
}

export interface AbsenceResponse {
  id: string;
  employee_id: string;
  start_date: string;  // YYYY-MM-DD
  end_date: string;
  reason_id: string;
  reason_code: string;
  reason_label: string;
  reason_is_planned: boolean;
  reason_color: string | null;
  hours_total: number | null;
}

export interface AbsenceCreateRequest {
  employee_id: string;
  start_date: string;
  end_date: string;
  reason_id: string;
  hours_total?: number;
}

export interface RoleRuleIn {
  role: string | null;
  work_type_id: string;
  percent_of_norm: number;
}

export interface RoleRulesBatchRequest {
  rules: RoleRuleIn[];
}

export interface EmployeeRuleIn {
  work_type_id: string;
  percent_of_norm: number;
}

export interface EmployeeRulesBatchRequest {
  employee_rules: { employee_id: string; rules: EmployeeRuleIn[] }[];
}

export interface RoleRulesValidationError {
  role: string | null;
  sum: number;
  expected: number;
}

export interface EmployeeRulesValidationError {
  employee_id: string;
  sum: number;
  expected: number;
}

export interface MandatoryWorkType {
  id: string;
  code: string;
  label: string;
  is_active: boolean;
  sort_order: number;
  subtracts_from_pool: boolean;
  is_system: boolean;
}

export interface MandatoryWorkTypeCreate {
  code: string;
  label: string;
  is_active?: boolean;
  sort_order?: number;
  subtracts_from_pool?: boolean;
}

export interface MandatoryWorkTypeUpdate {
  code?: string;
  label?: string;
  is_active?: boolean;
  sort_order?: number;
  subtracts_from_pool?: boolean;
}

export interface RoleCapacityRule {
  id: string;
  year: number;
  quarter: number;
  role: EmployeeRole | null;
  work_type_id: string;
  percent_of_norm: number;
}

export interface RoleCapacityRuleCreate {
  year: number;
  quarter: number;
  role: EmployeeRole | null;
  work_type_id: string;
  percent_of_norm: number;
}

export interface EmployeeCapacityOverride {
  id: string;
  year: number;
  quarter: number;
  employee_id: string;
  work_type_id: string;
  percent_of_norm: number;
}

export interface EmployeeCapacityOverrideCreate {
  year: number;
  quarter: number;
  employee_id: string;
  work_type_id: string;
  percent_of_norm: number;
}

export interface CopyRulesRequest {
  from_year: number;
  from_quarter: number;
  to_year: number;
  to_quarter: number;
}

export interface CopyRulesResponse {
  created: number;
}

export interface MonthlyCapacityResponse {
  employee_id: string;
  employee_name: string;
  year: number;
  month: number;
  workdays: number;
  norm_hours: number;
  vacation_hours: number;
  mandatory_hours: number;
  available_hours: number;
  fact_hours: number;
}

export interface QuarterCapacityResponse {
  employee_id: string;
  employee_name: string;
  year: number;
  quarter: number;
  team: string | null;
  months: MonthlyCapacityResponse[];
  total_norm_hours: number;
  total_vacation_hours: number;
  total_mandatory_hours: number;
  total_available_hours: number;
  total_fact_hours: number;
}

// === Backlog ===

export type BacklogImpactRisk = 'low' | 'medium' | 'high';

export type BacklogView = 'active' | 'archived' | 'in_work' | 'quarterly';

export interface BacklogItemScenarioRef {
  id: string;
  name: string;
}

export interface BacklogItemResponse {
  id: string;
  title: string;
  project_id: string | null;
  issue_id: string | null;
  jira_key: string | null;
  priority: number | null;
  estimate_hours: number | null;
  estimate_analyst_hours: number | null;
  estimate_dev_hours: number | null;
  estimate_qa_hours: number | null;
  estimate_opo_hours: number | null;
  opo_analyst_ratio: number | null;
  impact: BacklogImpactRisk | null;
  risk: BacklogImpactRisk | null;
  archived_at: string | null;
  in_work: boolean;
  approved_scenarios: BacklogItemScenarioRef[];
  assignee_employee_id: string | null;
  assignee_display_name: string | null;
  customer: string | null;
  jira_status: string | null;
  jira_status_category: string | null;
  jira_status_changed_at: string | null;
  goals: string | null;
  quarter_label: string | null;
  // Planning parameters — effective values (from Jira or manual override).
  // Override via PATCH /backlog/{id}; sync no longer wipes manual values when Jira is empty.
  involvement_analyst: number | null;
  involvement_dev: number | null;
  involvement_qa: number | null;
  involvement_launch: number | null;
  duration_analyst_days: number | null;
  duration_dev_days: number | null;
  duration_qa_days: number | null;
  duration_launch_days: number | null;
  // Current Jira values (for badge "from Jira" vs "manual override").
  involvement_analyst_jira: number | null;
  involvement_dev_jira: number | null;
  involvement_qa_jira: number | null;
  involvement_launch_jira: number | null;
  duration_analyst_days_jira: number | null;
  duration_dev_days_jira: number | null;
  duration_qa_days_jira: number | null;
  duration_launch_days_jira: number | null;
  // Parallel staffing overrides (null = inherit from project default, which defaults to 1).
  parallel_count_analyst: number | null;
  parallel_count_dev: number | null;
  parallel_count_qa: number | null;
  // Hierarchy flags for RFA-row expansion in UI.
  planning_mode: 'whole' | 'by_epics';
  included_in_planning: boolean;
  has_parent_in_backlog: boolean;
  has_children_in_backlog: boolean;
}

export interface BacklogRefreshResult {
  created: number;
  updated: number;
  removed: number;
  archived: number;
  restored: number;
  jira_refreshed: number;
}

// === Planning ===

export type ScenarioStatus = 'draft' | 'approved';

export interface ScenarioResponse {
  id: string;
  name: string;
  quarter: string | null;
  year: number | null;
  status: ScenarioStatus;
  team: string | null;
  external_qa_hours: number | null;
}

export interface ResourceDayHours {
  date: string; // ISO "YYYY-MM-DD"
  hours: number;
}

export interface ResourceEmployee {
  employee_id: string;
  display_name: string;
  role: string | null;
  total_hours: number;
  days: ResourceDayHours[];
}

export interface ResourceBase {
  year: number;
  quarter: number;
  team: string;
  employees: ResourceEmployee[];
  role_totals: Record<string, number>;
  external_qa_hours: number | null;
}

export interface WorkTypeRow {
  work_type_id: string;
  work_type_label: string;
  subtracts_from_pool: boolean;
  by_role: Record<string, number>;
  by_role_pct: Record<string, number | null>;
  total: number;
}

export interface ResourceSummaryOut {
  year: number;
  quarter: number;
  team: string;
  roles: string[];
  role_employee_names: Record<string, string[]>;
  total_by_role: Record<string, number>;
  total: number;
  work_type_rows: WorkTypeRow[];
  available_for_backlog_by_role: Record<string, number>;
  available_for_backlog_total: number;
  external_qa_hours: number | null;
  calendar_gross_by_role: Record<string, number>;
  absence_days_by_employee: Array<{
    employee_id: string;
    display_name: string;
    role: string | null;
    planned_days: number;
    unplanned_days: number;
  }>;
}

export interface AllocationResponse {
  id: string;
  scenario_id: string;
  backlog_item_id: string;
  included: boolean;
  planned_hours: number | null;
  title: string;
  jira_key: string | null;
  priority: number | null;
  estimate_hours: number | null;
  estimate_analyst_hours: number | null;
  estimate_dev_hours: number | null;
  estimate_qa_hours: number | null;
  estimate_opo_hours: number | null;
  override_estimate_analyst_hours: number | null;
  override_estimate_dev_hours: number | null;
  override_estimate_qa_hours: number | null;
  override_estimate_opo_hours: number | null;
  opo_analyst_ratio: number | null;
  impact: BacklogImpactRisk | null;
  risk: BacklogImpactRisk | null;
  assignee_employee_id: string | null;
  assignee_display_name: string | null;
  assignee_role: string | null;
  customer: string | null;
  cost_type: string | null;
  source_category: string | null;
  status: string | null;
  status_category: string | null;
  issue_id: string | null;
  has_children_in_backlog: boolean;
}

// === Scenario rules ===

export interface ScenarioRuleOut {
  id: string;
  role: string | null;
  work_type_id: string;
  percent_of_norm: number;
}

export interface ScenarioRuleInput {
  role: string | null;
  work_type_id: string;
  percent_of_norm: number;
}

// === Capacity diff ===

export interface AbsenceChange {
  type: 'added' | 'removed';
  start_date: string;
  end_date: string;
  reason: string | null;
  hours: number;
}

export interface MonthDiff {
  year: number;
  month: number;
  snapshot_available_hours: number;
  current_available_hours: number;
  delta_hours: number;
  absence_changes: AbsenceChange[];
}

export interface EmployeeDiff {
  employee_id: string;
  employee_name: string;
  months: MonthDiff[];
}

export interface CapacityDiffResponse {
  has_changes: boolean;
  changed_employees: EmployeeDiff[];
}

// === Scenario revision history ===

export interface ScenarioRevisionItem {
  backlog_item_id: string | null;
  backlog_item_name: string;
  action: 'included' | 'excluded';
}

export interface ScenarioCapacitySnapshot {
  employee_id: string | null;
  employee_name: string;
  year: number;
  month: number;
  norm_hours: number;
  available_hours: number;
}

export interface ScenarioRevision {
  id: string;
  revision_number: number;
  approved_at: string;
  note: string | null;
  items: ScenarioRevisionItem[];
  capacity_snapshots: ScenarioCapacitySnapshot[];
}

export interface RevisionDiffItem {
  backlog_item_id: string | null;
  backlog_item_name: string;
}

export interface RevisionDiffMonth {
  year: number;
  month: number;
  r1_norm_hours: number;
  r1_available_hours: number;
  r2_norm_hours: number;
  r2_available_hours: number;
  delta_norm_hours: number;
  delta_available_hours: number;
}

export interface RevisionDiffEmployee {
  employee_id: string | null;
  employee_name: string;
  months: RevisionDiffMonth[];
  delta_total_norm_hours: number;
  delta_total_available_hours: number;
}

export interface RevisionDiffSide {
  revision_number: number;
  approved_at: string;
  note: string | null;
  included_count: number;
}

export interface RevisionDiffResponse {
  r1: RevisionDiffSide;
  r2: RevisionDiffSide;
  added: RevisionDiffItem[];
  removed: RevisionDiffItem[];
  kept: RevisionDiffItem[];
  capacity: RevisionDiffEmployee[];
}

// === Hierarchy rules ===

export interface HierarchyRule {
  id: string;
  priority: number;
  project_key: string | null;
  issue_type: string | null;
  require_no_parent: boolean;
  is_container: boolean;
  is_enabled: boolean;
  description: string | null;
}

export interface HierarchyRuleCreate {
  priority: number;
  project_key: string | null;
  issue_type: string | null;
  require_no_parent: boolean;
  is_container: boolean;
  is_enabled: boolean;
  description: string | null;
}

export type HierarchyRuleUpdate = Partial<HierarchyRuleCreate>;

// === Production calendar ===

export interface ProductionCalendarDayResponse {
  date: string;         // YYYY-MM-DD
  is_workday: boolean;
  kind: string;
  hours: number;
  note: string | null;
  source: 'xmlcalendar' | 'manual';
}

export interface ProductionCalendarUpsertRequest {
  date: string;
  is_workday: boolean;
  kind: string;
  hours?: number | null;
  note: string | null;
}

export interface ProductionCalendarSyncResponse {
  inserted: number;
  updated: number;
  skipped_manual: number;
}

// ─── Quarter period ───────────────────────────────────────────────────────

export interface QuarterPeriod {
  year: number;
  quarter: 1 | 2 | 3 | 4;
  month?: number; // if set, must be a month belonging to the selected quarter (enforced by QuarterPicker)
}

export function periodToParams(p: QuarterPeriod): Record<string, string> {
  const params: Record<string, string> = {
    year: String(p.year),
    quarter: String(p.quarter),
  };
  if (p.month) params.month = String(p.month);
  return params;
}

export function currentQuarterPeriod(): QuarterPeriod {
  const now = new Date();
  const m = now.getMonth() + 1; // 1-12
  const q = m <= 3 ? 1 : m <= 6 ? 2 : m <= 9 ? 3 : 4;
  return { year: now.getFullYear(), quarter: q as 1 | 2 | 3 | 4 };
}

// ─── Dashboard response types ─────────────────────────────────────────────

export interface ProjectAssignee {
  initials: string;
  color: string;
}

export interface ProjectItem {
  issue_key: string;
  title: string;
  status: string;
  status_category: 'done' | 'indeterminate' | 'new' | 'overdue';
  plan_hours: number;
  fact_hours: number;
  delta_hours: number;
  subtasks_done: number;
  subtasks_total: number;
  assignees: ProjectAssignee[];
  assignees_total: number;
  due_date: string | null;
  days_to_due: number | null;
  trend_hours_week: number;
  trend_dir: 'up' | 'down' | 'flat';
  forecast_close_date: string | null;
  forecast_in_quarter: boolean;
  silent_days: number;
  weekly_activity: number[];
  team_fact_hours: number;
  alien_fact_hours: number;
  alien_helpers: ProjectAssignee[];
  alien_helper_count: number;
}

export interface DashboardProjectsResponse {
  total: number;
  done: number;
  in_progress: number;
  overdue: number;
  not_started: number;
  total_fact_hours: number;
  total_plan_hours: number;
  avg_load_pct: number;
  silent_count: number;
  forecast_done: number;
  forecast_pct: number;
  projects: ProjectItem[];
  total_team_fact_hours: number;
  total_alien_fact_hours: number;
  alien_helper_count: number;
  alien_projects_count: number;
}

export interface NormWorkTypeBreakdown {
  work_type_id: string;
  work_type_code?: string | null;
  label: string;
  plan_hours: number;
  fact_hours: number;
  pct: number;
}

export interface NormWorkEmployee {
  employee_id: string;
  name: string;
  initials: string;
  plan_hours: number;
  fact_hours: number;
  pct: number;
  foreign_hours: number;
  foreign_pct: number;
  work_types: NormWorkTypeBreakdown[];
}

export interface NormWorkRoleGroup {
  role_code: string;
  role_label: string;
  role_color: string;
  employees_count: number;
  total_plan: number;
  total_fact: number;
  total_pct: number;
  foreign_hours: number;
  foreign_pct: number;
  employees: NormWorkEmployee[];
}

export interface DashboardNormWorkResponse {
  roles: NormWorkRoleGroup[];
  total_plan: number;
  total_fact: number;
  total_pct: number;
  foreign_hours: number;
  foreign_pct: number;
}

export interface CategoryMetaItem {
  key: string;
  label: string;
  color: string;
  hours: number;
  worklog_count: number;
  issue_count: number;
  employee_count: number;
  avg_worklog_minutes: number;
  pct: number;
}

export interface EmployeeWorklogActivity {
  employee_id: string;
  name: string;
  initials: string;
  last_worklog_at: string | null;
  days_since_last: number | null;
  is_absent: boolean;
  absence_label: string | null;
}

export interface DashboardCategoriesResponse {
  items: CategoryMetaItem[];
  total_hours: number;
  employees: EmployeeWorklogActivity[];
}

// ─── Analytics hierarchical report ───────────────────────────────────────────

export interface NodeTotals {
  fact_hours: number;
  plan_hours: number | null;
  pct_plan: number | null;
  pct_total: number;
  pct_in_group: number | null;
  worklog_count: number;
  issue_count: number;
  employee_count: number;
  avg_worklog_minutes: number;
  foreign_issue_count: number;
  foreign_hours: number;
  foreign_pct: number;
}

export interface AnalyticsIssueNode {
  id: string;
  key: string;
  summary: string;
  status: string;
  status_category: string | null;
  issue_type: string;
  category: string | null;
  last_worklog_at: string | null;
  assignee_name: string | null;
  is_foreign: boolean;
  team: string | null;
  totals: NodeTotals;
}

export interface AnalyticsCategoryNode {
  category_code: string | null;
  label: string;
  color: string;
  totals: NodeTotals;
  issues: AnalyticsIssueNode[];
}

export interface AnalyticsWorkTypeNode {
  work_type_id: string;
  label: string;
  totals: NodeTotals;
  categories: AnalyticsCategoryNode[];
}

export interface AnalyticsEmployeeNode {
  employee_id: string;
  name: string;
  initials: string;
  totals: NodeTotals;
  work_types: AnalyticsWorkTypeNode[];
}

export interface AnalyticsRoleNode {
  role_code: string | null;
  role_label: string;
  role_color: string;
  totals: NodeTotals;
  employees: AnalyticsEmployeeNode[];
}

export interface AnalyticsTeamNode {
  team: string | null;
  totals: NodeTotals;
  roles: AnalyticsRoleNode[];
}

export interface AnalyticsReportResponse {
  teams: AnalyticsTeamNode[];
  grand_totals: NodeTotals;
}

export interface IssueWorklogItem {
  worklog_id: string;
  started_at: string;
  hours: number;
  employee_name: string;
  comment: string | null;
}

// ─── Issue Context (drawer) ───────────────────────────────────────────────

export interface IssueContextAncestor {
  id: string;
  key: string;
  summary: string;
  issue_type: string;
}

export interface IssueContextChild {
  id: string;
  key: string;
  summary: string;
  status: string;
  status_category: string | null;
  issue_type: string;
  category: string | null;
  assigned_category: string | null;
  include_in_analysis: boolean;
  subtree_count: number;
}

export interface IssueContextResponse {
  id: string;
  key: string;
  summary: string;
  status: string;
  status_category: string | null;
  issue_type: string;
  category: string | null;
  assigned_category: string | null;
  include_in_analysis: boolean;
  is_container: boolean;
  ancestors: IssueContextAncestor[];
  siblings_total: number;
  children: IssueContextChild[];
  subtree_count: number;
  description?: string | null;
  goals?: string | null;
}

export interface IssueChildNode {
  id: string;
  key: string;
  summary: string;
  status: string;
  status_category: string | null;
  issue_type: string;
  category: string | null;
  assigned_category: string | null;
  include_in_analysis: boolean;
}

// === Bulk triage operations ===

export type BulkFilter = {
  project_keys?: string[];
  teams?: string[];
  statuses?: string[];
  status_changed_before?: string;
  only_unverified?: boolean;
  only_no_assigned?: boolean;
};

export type BulkPreviewItem = {
  id: string;
  key: string;
  summary: string;
  status: string;
  status_changed_at: string | null;
  category: string | null;
  assigned_category: string | null;
  project_key: string;
};

export type BulkPreviewResponse = {
  total: number;
  truncated: boolean;
  items: BulkPreviewItem[];
};

export type BulkApplyResponse = { updated: number; archived_ids: string[] };
export type BulkAcceptResponse = { applied: number; skipped_no_suggestion: number };
export type BulkCascadeResponse = { applied: number; skipped_ancestors: number };
