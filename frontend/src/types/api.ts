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
}

export interface MandatoryWorkTypeCreate {
  code: string;
  label: string;
  is_active?: boolean;
  sort_order?: number;
}

export interface MandatoryWorkTypeUpdate {
  code?: string;
  label?: string;
  is_active?: boolean;
  sort_order?: number;
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

export type BacklogView = 'active' | 'archived';

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
  jira_status: string | null;
  jira_status_category: string | null;
  jira_status_changed_at: string | null;
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
  absence_days_by_employee: Array<{ employee_id: string; display_name: string; role: string | null; days: number }>;
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
  opo_analyst_ratio: number | null;
  impact: BacklogImpactRisk | null;
  risk: BacklogImpactRisk | null;
  assignee_employee_id: string | null;
  assignee_display_name: string | null;
  customer: string | null;
  cost_type: string | null;
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
