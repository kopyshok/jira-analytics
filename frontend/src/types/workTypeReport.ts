/** TS types for thematic work-type report — mirrors app/schemas/work_type_report.py */

export type GroupingDim = 'theme' | 'team' | 'role' | 'employee' | 'project' | 'issue';

// ---- Themes ----

export interface ThemeOut {
  id: string;
  work_type_id: string;
  name: string;
  description: string | null;
  color: string;
  sort_order: number;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ThemeCreateRequest {
  work_type_id: string;
  name: string;
  description?: string | null;
  color?: string;
  sort_order?: number;
}

export interface ThemeUpdateRequest {
  name?: string;
  description?: string | null;
  color?: string;
  sort_order?: number;
}

export interface ThemeMergeRequest {
  target_theme_id: string;
}

/** Кандидат из ведра «Другое» — возвращается /themes GET вместе со словарём */
export interface ThemeCandidate {
  proposed_name: string;
  issues_count: number;
  hours: number;
  sample_keys: string[];
  snapshot_id: string;
}

export interface ThemeListResponse {
  themes: ThemeOut[];
  candidates: ThemeCandidate[];
}

// ---- Snapshot data shapes ----

export interface TopEmployee {
  employee_id: string;
  full_name: string;
  hours: number;
  pct: number;
}

export interface TopTask {
  issue_id: string;
  key: string;
  summary: string;
  hours: number;
}

export interface ThemeIssue {
  issue_id: string;
  key: string;
  summary: string;
  hours: number;
  [key: string]: unknown;
}

export interface ThemeTotals {
  hours: number;
  tasks: number;
  employees_count: number;
  pct_of_work_type: number;
}

export interface Theme {
  theme_id: string | null;
  theme_name: string;
  is_new: boolean;
  is_low_confidence: boolean;
  totals: ThemeTotals;
  top_employees: TopEmployee[];
  top_tasks: TopTask[];
  issues: ThemeIssue[];
  evidence_keys: string[];
  narrative: string;
}

export interface Outlier {
  key: string;
  issue_id: string;
  reason: string;
  value: number | string;
  context: Record<string, unknown> | null;
  explanation: string;
}

/** Кандидат во frontend-вариации (без snapshot_id — он живёт на корне ответа) */
export interface Candidate {
  proposed_name: string;
  issues_count: number;
  hours: number;
  sample_keys: string[];
}

export interface ManualReviewIssue {
  issue_id: string;
  key: string;
  summary: string;
  hours: number;
  failure_reason: string;
}

export interface ReportTotals {
  hours: number;
  tasks: number;
  employees: number;
  themes_count: number;
}

export interface WorkTypeReportData {
  headline: string;
  totals: ReportTotals;
  themes: Theme[];
  candidates: Candidate[];
  outliers: Outlier[];
  recommendation: { text: string; expected_impact: string };
  manual_review_required: ManualReviewIssue[];
  is_fallback_narrative: boolean;
}

// ---- Report request / response ----

export interface WorkTypeReportRequest {
  work_type_id: string;
  year: number;
  quarter: number;
  month?: number | null;
  teams?: string[];
  force_refresh?: boolean;
}

export interface WorkTypeReportResponse {
  snapshot_id: string;
  work_type_id: string;
  year: number;
  quarter: number;
  month: number | null;
  start_date: string;
  end_date: string;
  team_set: string[];
  generated_at: string;
  model_id: string | null;
  prompt_version: string | null;
  dictionary_version: number;
  is_stale: boolean;
  data: WorkTypeReportData;
}

// ---- Candidate actions ----

export interface CandidateAcceptRequest {
  snapshot_id: string;
  proposed_name: string;
  new_theme_name?: string | null;
  color?: string;
}

export interface CandidateMergeRequest {
  snapshot_id: string;
  proposed_name: string;
  target_theme_id: string;
}

export interface CandidateIgnoreRequest {
  snapshot_id: string;
  proposed_name: string;
}

export interface ManualClassifyRequest {
  issue_id: string;
  work_type_id: string;
  theme_id?: string | null;
  contribution_text?: string | null;
}

// ---- Layouts ----

export interface LayoutOut {
  id: string;
  user_id: string;
  work_type_id: string;
  name: string;
  grouping_dims: GroupingDim[];
  visible_columns: string[] | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface LayoutCreateRequest {
  work_type_id: string;
  name: string;
  grouping_dims: GroupingDim[];
  visible_columns?: string[] | null;
  is_default?: boolean;
}

export interface LayoutUpdateRequest {
  name?: string;
  grouping_dims?: GroupingDim[];
  visible_columns?: string[] | null;
  is_default?: boolean;
}
