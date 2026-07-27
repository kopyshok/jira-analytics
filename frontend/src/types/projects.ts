export interface ProjectListItem {
  key: string;
  summary: string;
  status: string;
  status_category: 'new' | 'indeterminate' | 'done' | null;
  category: string;
  period_start: string | null;
  period_end: string | null;
  total_hours: number;
  child_count: number;
  employee_count: number;
  rating_quality: number | null;
  rating_speed: number | null;
  rating_result: number | null;
}

export interface CategoryBreakdown {
  code: string;
  label: string;
  color: string | null;
  hours: number;
  pct: number;
}

export interface EmployeeBreakdown {
  employee_id: string;
  name: string;
  hours: number;
  pct: number;
}

export interface TopIssue {
  key: string;
  summary: string;
  hours: number;
}

export interface IssueHours {
  key: string;
  hours: number;
}

export interface ProjectDetail {
  key: string;
  summary: string;
  description: string | null;
  status: string;
  status_category: 'new' | 'indeterminate' | 'done' | null;
  period_start: string | null;
  period_end: string | null;
  planned_start_date: string | null;
  planned_end_date: string | null;
  total_hours: number;
  weeks: number;
  child_count: number;
  employee_count: number;
  categories: CategoryBreakdown[];
  employees: EmployeeBreakdown[];
  top_issues: TopIssue[];
  issue_hours_by_key: IssueHours[];
  rating_quality: number | null;
  rating_speed: number | null;
  rating_result: number | null;
}

export type WorkBucket = 'analysis' | 'development' | 'testing' | 'ope';

export interface ChecklistItem {
  label: string;
  done: boolean;
  category: WorkBucket;
}

export interface WorkBreakdownGroup {
  bucket: WorkBucket;
  label: string;
  child_keys: string[];
}

export interface ProjectSummary {
  goals: string[];
  result_checklist: ChecklistItem[];
  status_text: string;
  workload_summary: string;
  work_breakdown: WorkBreakdownGroup[];
  generated_at: string;
  model_used: string;
}

export interface PlanWorkType {
  code: 'analyst' | 'dev' | 'qa';
  label: string;
  plan_hours: number;
  fact_hours: number;
  pct: number | null;
}

export interface TimelineBar {
  phase: string;
  label: string;
  start_date: string;
  end_date: string;
}

export interface TimelineRow {
  key: string | null;
  title: string | null;
  status: string | null;
  bars: TimelineBar[];
}

export interface PlanTimeline {
  start: string | null;
  end: string | null;
  quarter_start: string;
  quarter_end: string;
  rows: TimelineRow[];
}

export interface PlanChild {
  key: string;
  title: string | null;
  status: string | null;
  jira_url: string | null;
  hours: number;
}

export interface ProjectPlan {
  key: string;
  work_types: PlanWorkType[];
  external_hours: number;
  total_plan: number | null;
  total_fact: number;
  total_pct: number | null;
  timeline: PlanTimeline;
  children: PlanChild[];
}

export interface PortfolioSignal {
  kind: 'overload' | 'silent' | 'lagging';
  text: string;
  severity: 'warn' | 'info';
}

export interface Portfolio {
  project_count: number;
  work_types: PlanWorkType[];
  external_hours: number;
  total_plan: number | null;
  total_fact: number;
  total_pct: number | null;
  timeline: PlanTimeline;
  signals: PortfolioSignal[];
}

/** Фильтры списка проектов — общие для списка и сводки портфеля. */
export interface ProjectListFiltersState {
  search: string;
  statusCategory: string;
  category: string;
  year: number;
  quarter: number;
}
