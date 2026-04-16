// === Employees & Projects ===

export interface EmployeeResponse {
  id: string;
  display_name: string;
  email: string | null;
  is_active: boolean;
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
  last_sync: string | null;
  cursor: string | null;
  last_error: string | null;
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
  project_key: string;
  parent_key: string | null;
  assigned_category: string | null;
  category: string | null;
  include_in_analysis: boolean;
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

export interface VacationResponse {
  id: string;
  employee_id: string;
  start_date: string;
  end_date: string;
  hours_total: number | null;
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
}

export interface QuarterCapacityResponse {
  employee_id: string;
  employee_name: string;
  year: number;
  quarter: number;
  months: MonthlyCapacityResponse[];
  total_norm_hours: number;
  total_vacation_hours: number;
  total_mandatory_hours: number;
  total_available_hours: number;
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
