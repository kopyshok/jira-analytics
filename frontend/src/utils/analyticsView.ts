/**
 * Правила «Иерархического отчёта по часам», общие для раскладок страницы:
 * границы периода, параметры выгрузки в XLSX, тон «% план», русский формат
 * часов и процентов в компактном виде скинов. Чистые функции — под тесты.
 */

/** Границы квартала (или месяца внутри него) в виде ISO-дат. */
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

export interface AnalyticsExportInput {
  period: { year: number; quarter: number; month?: number | null };
  startDate?: string;
  endDate?: string;
  selectedTeam: string;
  selectedTeams: string[];
  selectedSubgroups: string[];
  employeeId?: string;
  taskQ?: string;
  workType?: string;
  category?: string;
  visibleColumns: string[];
  hierarchy: boolean;
}

/**
 * Параметры выгрузки отчёта: тот же срез, что на экране, плюс видимые колонки.
 * Команда из списка на странице главнее командного фильтра шапки.
 */
export function analyticsExportParams(i: AnalyticsExportInput): URLSearchParams {
  return new URLSearchParams({
    year: String(i.period.year),
    quarter: String(i.period.quarter),
    ...(i.period.month != null ? { month: String(i.period.month) } : {}),
    ...(i.startDate ? { start_date: i.startDate } : {}),
    ...(i.endDate ? { end_date: i.endDate } : {}),
    ...(i.selectedTeam !== 'all'
      ? { teams: i.selectedTeam }
      : i.selectedTeams.length ? { teams: i.selectedTeams.join(',') } : {}),
    ...(i.selectedSubgroups.length ? { subgroups: i.selectedSubgroups.join(',') } : {}),
    ...(i.employeeId ? { employee_id: i.employeeId } : {}),
    ...(i.taskQ ? { task_query: i.taskQ } : {}),
    ...(i.workType ? { work_type_codes: i.workType } : {}),
    ...(i.category ? { category_codes: i.category } : {}),
    ...(i.visibleColumns.length ? { columns: i.visibleColumns.join(',') } : {}),
    ...(i.hierarchy ? { hierarchy: 'true' } : {}),
  });
}

/** Категории, у задач которых есть своя страница проекта. */
const PROJECT_CATEGORIES = new Set(['quarterly_tasks', 'archive_target']);

export function isProjectCategory(code: string | null | undefined): boolean {
  return PROJECT_CATEGORIES.has(code ?? '');
}

export type PlanTone = 'over' | 'under' | 'ok';

/**
 * Тон «% план» в компактном виде: больше 110 % — перерасход (тревожно),
 * меньше 70 % — недобор (тихо-предупреждающе), между ними — без выделения.
 */
export function planTone(pct: number | null | undefined): PlanTone | null {
  if (pct == null) return null;
  if (pct > 110) return 'over';
  if (pct < 70) return 'under';
  return 'ok';
}

const RU_1 = new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const RU_0 = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });

/** Часы с одним знаком: «1 240,0». */
export const formatHours = (value: number): string => RU_1.format(value);

/** Целое с разрядами: «1 320». */
export const formatInt = (value: number): string => RU_0.format(Math.round(value));

/** Процент целым: «94%». */
export const formatPct = (value: number): string => `${RU_0.format(Math.round(value))}%`;

/** Процент с одним знаком: «56,7%». */
export const formatPct1 = (value: number): string => `${RU_1.format(value)}%`;

/** «2026-10-14…» → «14.10.2026»; пустое и неразборчивое — «—». */
export function formatIsoDate(iso: string | null | undefined): string {
  const m = (iso ?? '').match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : '—';
}
