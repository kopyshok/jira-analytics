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
  rating_quality: number | null;
  rating_speed: number | null;
  rating_result: number | null;
}

export interface FlowBlock {
  label: string;
  status: 'source' | 'flow' | 'done';
}

export interface ChecklistItem {
  label: string;
  done: boolean;
}

export interface ProjectSummary {
  goals: string[];
  result_flow_blocks: FlowBlock[];
  result_checklist: ChecklistItem[];
  status_text: string;
  workload_summary: string;
  generated_at: string;
  model_used: string;
}
