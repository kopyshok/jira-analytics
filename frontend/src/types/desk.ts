// Контракты публичного рабочего стола аналитика (/desk/:token).
// Поля сверены с app/services/work_desk_widgets.py.

export interface DeskEmployee {
  id: string;
  display_name: string;
  avatar_url: string | null;
}

export interface DeskPeriod {
  year: number;
  quarter: number;
}

export interface DeskSummary {
  /** Накопительный баланс факт−норма с 1 января (знаковый). */
  overtime_hours: number;
  /** Рабочих дней до конца текущего месяца включительно. */
  remaining_workdays_month: number;
  /** Незавершённых проектов сотрудника на свежем плане. */
  projects_in_progress: number;
}

export interface DeskMeta {
  employee: DeskEmployee;
  teams: string[];
  enabled_widgets: string[];
  period: DeskPeriod;
  summary: DeskSummary;
}

export interface ProjectChild {
  key: string | null;
  title: string | null;
  jira_url: string | null;
  status: string | null;
  fact_hours: number;
}

/** Проект/назначение сотрудника (общая форма для my_tasks и team_availability). */
export interface DeskProject {
  key: string | null;
  issue_id?: string | null;
  title: string | null;
  jira_url: string | null;
  status: string | null;
  start_date: string | null;
  end_date: string | null;
  norm_hours: number;
  fact_hours: number;
  pct: number;
  children?: ProjectChild[];
}

export interface MyTasksData {
  projects: DeskProject[];
}

export interface TimelineBar {
  key: string | null;
  title: string | null;
  start_date: string;
  end_date: string;
  status: string | null;
  fact_start: string | null;
  fact_end: string | null;
}
export interface MyTimelineData {
  quarter_start: string;
  quarter_end: string;
  bars: TimelineBar[];
}

export interface BalanceDay {
  date: string;
  kind: string;
  delta: number;
}
export interface HoursBalanceData {
  balance_hours: number;
  days: BalanceDay[];
}

export interface WorkTypeIssue {
  key: string | null;
  title: string | null;
  jira_url: string | null;
  status: string | null;
  fact_hours: number;
}
export interface WorkTypeCategory {
  label: string;
  color: string;
  fact_hours: number;
  issues: WorkTypeIssue[];
}
export interface WorkTypeSlice {
  label: string;
  plan_hours: number;
  fact_hours: number;
  pct: number;
  categories: WorkTypeCategory[];
}
export interface CategoryBreakdownData {
  work_types: WorkTypeSlice[];
}

export interface DeskAbsenceEmployee {
  id: string;
  display_name: string;
}
export interface DeskAbsence {
  employee_id: string;
  employee_name: string;
  start_date: string;
  end_date: string;
  reason_label: string;
  reason_color: string | null;
}
export interface TeamAbsencesData {
  employees: DeskAbsenceEmployee[];
  absences: DeskAbsence[];
  year: number;
  quarter: number;
}

export interface AvailabilityMember {
  id: string;
  display_name: string;
  projects: DeskProject[];
}
export interface TeamAvailabilityData {
  members: AvailabilityMember[];
  quarter_start: string;
  quarter_end: string;
}

export interface CalendarDay {
  date: string;
  kind: string;
  hours: number;
}
export interface ProductionCalendarData {
  quarter_workdays: number;
  month_workdays: number;
  quarter_work_hours: number;
  month_work_hours: number;
  days: CalendarDay[];
}

export interface AwaitingItem {
  key: string | null;
  title: string | null;
  status: string | null;
  last_comment_at: string | null;
  last_comment_author: string | null;
}
export interface AwaitingReactionData {
  items: AwaitingItem[];
}
