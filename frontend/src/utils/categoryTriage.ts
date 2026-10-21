/**
 * Разбор задач (/categories): верхние строки очереди приходят с сервера
 * страницей. В «К разбору» рабочей базы десятки тысяч верхних строк —
 * целиком их нельзя ни передавать, ни рисовать. Отбор («Скрытые статусы»,
 * «Только переехавшие») и сортировка колонок поэтому считаются на сервере по
 * всей очереди, а здесь — только сборка запроса и порядок раскрытых подзадач.
 */

export type TriageTab = 'stack' | 'active' | 'initiatives' | 'archive_target' | 'archive';
export type RootSortField = 'status_changed_at' | 'goals';
export type RootSort = { field: RootSortField; order: 'ascend' | 'descend' } | null;

export const ROOTS_PAGE_SIZES = [50, 100, 200];
export const ROOTS_DEFAULT_PAGE_SIZE = 100;

/** Параметры запроса страницы — они же ключ кэша. */
export interface RootsQuery {
  project_keys?: string;
  teams?: string;
  tab: TriageTab;
  search?: string;
  offset: string;
  limit: string;
  sort?: string;
  hidden_statuses?: string;
  only_moved?: string;
}

export function buildRootsQuery(input: {
  projectKeys?: string;
  teams?: string;
  tab: TriageTab;
  search?: string;
  page: number;
  pageSize: number;
  sort: RootSort;
  hiddenStatuses: string[];
  onlyMoved: boolean;
}): RootsQuery {
  const hidden = [...input.hiddenStatuses].sort();
  return {
    project_keys: input.projectKeys,
    teams: input.teams,
    tab: input.tab,
    search: input.search,
    offset: String((input.page - 1) * input.pageSize),
    limit: String(input.pageSize),
    sort: input.sort ? `${input.sort.order === 'descend' ? '-' : ''}${input.sort.field}` : undefined,
    hidden_statuses: hidden.length > 0 ? hidden.join(',') : undefined,
    only_moved: input.onlyMoved && input.tab === 'stack' ? 'true' : undefined,
  };
}

export const pageOfOffset = (offset: number, pageSize: number) => Math.floor(offset / pageSize) + 1;

/** Страница не дальше последней непустой (после разбора хвоста очереди). */
export const clampPage = (page: number, pageSize: number, total: number) =>
  Math.max(1, Math.min(page, Math.ceil(total / pageSize)));

type SortableRow = { status_changed_at: string | null; goals: string | null };

const COMPARE: Record<RootSortField, (a: SortableRow, b: SortableRow) => number> = {
  status_changed_at: (a, b) =>
    (a.status_changed_at ? new Date(a.status_changed_at).getTime() : 0)
    - (b.status_changed_at ? new Date(b.status_changed_at).getTime() : 0),
  goals: (a, b) => (a.goals ?? '').localeCompare(b.goals ?? ''),
};

/**
 * Порядок раскрытых подзадач по выбранной колонке. Верхние строки уже
 * отсортированы сервером, подзадачи приходят по ключу — их сортируем здесь.
 */
export function sortRows<T extends SortableRow>(rows: T[], sort: RootSort): T[] {
  if (!sort) return rows;
  const cmp = COMPARE[sort.field];
  const sign = sort.order === 'descend' ? -1 : 1;
  return [...rows].sort((a, b) => sign * cmp(a, b));
}
