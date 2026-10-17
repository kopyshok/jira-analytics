import type { Dayjs } from 'dayjs';
import type { NodeTotals } from '../types/api';

/** Returns ISO date bounds for a quarter (and optionally a specific month). */
export function periodBounds(year: number, quarter: number, month?: number): { start: string; end: string } {
  if (month != null) {
    const mm = String(month).padStart(2, '0');
    const lastDay = new Date(year, month, 0).getDate();
    return { start: `${year}-${mm}-01`, end: `${year}-${mm}-${lastDay}` };
  }
  const qStartMonth = (quarter - 1) * 3 + 1;
  const qEndMonth = qStartMonth + 2;
  const lastDay = new Date(year, qEndMonth, 0).getDate();
  return {
    start: `${year}-${String(qStartMonth).padStart(2, '0')}-01`,
    end: `${year}-${String(qEndMonth).padStart(2, '0')}-${lastDay}`,
  };
}

/** % выполнения плана по итогам отчёта; нет плана — null. */
export function planPercent(totals: NodeTotals): number | null {
  return totals.plan_hours && totals.plan_hours > 0
    ? (totals.fact_hours / totals.plan_hours) * 100
    : null;
}

/** Адрес выгрузки отчёта в XLSX — с теми же отборами, что на экране. */
export function analyticsExportUrl(apiBase: string, f: {
  period: { year: number; quarter: number; month?: number | null };
  localRange: [Dayjs | null, Dayjs | null] | null;
  selectedTeam: string;
  selectedTeams: string[];
  selectedSubgroups: string[];
  employeeId?: string;
  taskQ?: string;
  workType?: string;
  category?: string;
  visibleColumns: string[];
  hierarchy: boolean;
}): string {
  const p = new URLSearchParams({
    year: String(f.period.year),
    quarter: String(f.period.quarter),
    ...(f.period.month != null ? { month: String(f.period.month) } : {}),
    ...(f.localRange?.[0] ? { start_date: f.localRange[0].format('YYYY-MM-DD') } : {}),
    ...(f.localRange?.[1] ? { end_date: f.localRange[1].format('YYYY-MM-DD') } : {}),
    ...(f.selectedTeam !== 'all'
      ? { teams: f.selectedTeam }
      : f.selectedTeams.length ? { teams: f.selectedTeams.join(',') } : {}),
    ...(f.selectedSubgroups.length ? { subgroups: f.selectedSubgroups.join(',') } : {}),
    ...(f.employeeId ? { employee_id: f.employeeId } : {}),
    ...(f.taskQ ? { task_query: f.taskQ } : {}),
    ...(f.workType ? { work_type_codes: f.workType } : {}),
    ...(f.category ? { category_codes: f.category } : {}),
    ...(f.visibleColumns.length ? { columns: f.visibleColumns.join(',') } : {}),
    ...(f.hierarchy ? { hierarchy: 'true' } : {}),
  });
  return `${apiBase}/analytics/report/export.xlsx?${p.toString()}`;
}
