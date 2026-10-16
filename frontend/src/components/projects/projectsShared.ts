import type { ProjectListFiltersState, ProjectListItem } from '../../types/projects';

export const STATUS_CATEGORY_LABEL: Record<string, string> = {
  done: 'Готов',
  indeterminate: 'В работе',
  new: 'Новый',
};

export const CATEGORY_LABEL: Record<string, string> = {
  quarterly_tasks: 'Квартальные',
  archive_target: 'Архив',
};

/** «2026-10-01» → «окт. 26 г.» — месяц и год периода проекта. */
export function formatProjectMonth(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('ru-RU', { month: 'short', year: '2-digit' });
}

/** Средняя оценка проекта по трём шкалам (качество, скорость, результат); нет оценок — null. */
export function avgProjectRating(item: ProjectListItem): number | null {
  const values = [item.rating_quality, item.rating_speed, item.rating_result];
  if (values.every((v) => v == null)) return null;
  return Math.round(
    ((item.rating_quality ?? 0) + (item.rating_speed ?? 0) + (item.rating_result ?? 0))
      / values.filter((v) => v != null).length,
  );
}

/** Отборы экрана «Проекты» → параметры запросов списка и сводки портфеля. */
export function projectQueryParams(filters: ProjectListFiltersState) {
  return {
    search: filters.search || undefined,
    status_category: filters.statusCategory || undefined,
    category: filters.category || undefined,
    year: filters.year,
    quarter: filters.quarter,
  };
}

/** Склонение слова «проект» под число: 1 проект, 3 проекта, 5 проектов. */
export function pluralProjects(n: number): string {
  if (n % 100 >= 11 && n % 100 <= 14) return 'проектов';
  const last = n % 10;
  if (last === 1) return 'проект';
  if (last >= 2 && last <= 4) return 'проекта';
  return 'проектов';
}
