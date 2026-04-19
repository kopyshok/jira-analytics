// === Employees & Projects ===

export interface EmployeeResponse {
  id: string;
  jira_account_id: string;
  display_name: string;
  email: string | null;
  avatar_url: string | null;
  is_active: boolean;
  team: string | null;
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
  children: IssueTreeNode[];
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

export type AbsenceReason = 'vacation' | 'sick' | 'day_off' | 'other';

export interface AbsenceResponse {
  id: string;
  employee_id: string;
  start_date: string;
  end_date: string;
  reason: AbsenceReason;
  hours_total: number | null;
}

export interface AbsenceCreateRequest {
  employee_id: string;
  start_date: string;
  end_date: string;
  reason: AbsenceReason;
  hours_total?: number;
}

export interface CapacityRuleResponse {
  id: string;
  year: number;
  month: number;
  percent_of_norm: number;
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

export interface CategoryBreakdownResponse {
  employee_id: string;
  employee_name: string;
  by_bucket: {
    active_stack: number;
    initiatives: number;
    archive_target: number;
    archive_other: number;
    uncategorized: number;
  };
  total_hours: number;
}

// === Backlog ===

export interface BacklogItemResponse {
  id: string;
  title: string;
  project_id: string | null;
  quarter: string | null;
  year: number | null;
  estimate_hours: number | null;
  priority: number | null;
}

// === Planning ===

export interface ScenarioResponse {
  id: string;
  name: string;
  quarter: string | null;
  year: number | null;
}

export interface AllocationResponse {
  backlog_item_id: string;
  title: string;
  priority: number | null;
  estimate_hours: number;
  planned_hours: number;
  included: boolean;
  reason: string;
}

export interface PlanningResultResponse {
  scenario_id: string;
  scenario_name: string;
  year: number;
  quarter: number;
  total_capacity_hours: number;
  total_planned_hours: number;
  leftover_capacity_hours: number;
  included_count: number;
  skipped_count: number;
  allocations: AllocationResponse[];
}

export interface StoredAllocationResponse {
  id: string;
  scenario_id: string;
  backlog_item_id: string;
  planned_hours: number | null;
  included_flag: boolean;
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
