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

export interface DeskMeta {
  employee: DeskEmployee;
  teams: string[];
  enabled_widgets: string[];
  period: DeskPeriod;
}

export interface MyTask {
  key: string | null;
  title: string | null;
  phase: string | null;
  start_date: string | null;
  end_date: string | null;
  hours: number;
  jira_url: string | null;
}
export interface MyTasksData {
  tasks: MyTask[];
}

export interface MonthLoad {
  year: number;
  month: number;
  norm_hours: number;
  fact_hours: number;
}
export interface WeeklyLoadData {
  months: MonthLoad[];
}

export interface Conflict {
  type: string;
  window_start: string | null;
  window_end: string | null;
  metric_value: number | null;
  message: string | null;
}
export interface MyConflictsData {
  conflicts: Conflict[];
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

export interface UnloggedDay {
  date: string;
  expected_hours: number;
}
export interface UnloggedDaysData {
  days: UnloggedDay[];
}

export interface CategorySlice {
  label: string;
  hours: number;
}
export interface CategoryBreakdownData {
  categories: CategorySlice[];
}

export interface TeamAbsence {
  employee_name: string;
  start_date: string;
  end_date: string;
  reason_label: string;
  color: string | null;
}
export interface TeamAbsencesData {
  absences: TeamAbsence[];
}

export interface BusyBlock {
  label: string | null;
  start: string | null;
  end: string | null;
}
export interface AvailabilityMember {
  name: string;
  busy: BusyBlock[];
}
export interface TeamAvailabilityData {
  week_start: string;
  members: AvailabilityMember[];
}

export interface CalendarDay {
  date: string;
  kind: string;
  hours: number;
}
export interface ProductionCalendarData {
  quarter_workdays: number;
  remaining_workdays: number;
  days: CalendarDay[];
}

export interface DeadlineItem {
  key: string;
  title: string;
  due_date: string | null;
  status: string | null;
}
export interface QuarterDeadlinesData {
  items: DeadlineItem[];
}

export interface ExternalHelpTeam {
  team: string;
  hours: number;
}
export interface ExternalHelpData {
  own_hours: number;
  alien_hours: number;
  by_team: ExternalHelpTeam[];
}

export interface RecentChange {
  key: string | null;
  title: string | null;
  change: string | null;
  start_date: string | null;
  end_date: string | null;
}
export interface RecentChangesData {
  changes: RecentChange[];
}
