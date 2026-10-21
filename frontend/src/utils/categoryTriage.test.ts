import { describe, expect, it } from 'vitest';
import {
  buildRootsQuery,
  clampPage,
  pageOfOffset,
  sortRows,
  ROOTS_DEFAULT_PAGE_SIZE,
} from './categoryTriage';

const base = {
  projectKeys: 'OS,PMD',
  teams: undefined,
  tab: 'stack' as const,
  search: undefined,
  page: 1,
  pageSize: ROOTS_DEFAULT_PAGE_SIZE,
  sort: null,
  hiddenStatuses: [] as string[],
  onlyMoved: false,
};

describe('разбор задач: запрос страницы верхних строк', () => {
  it('просит у сервера одну страницу, а не всю очередь', () => {
    expect(buildRootsQuery({ ...base, page: 3 })).toEqual({
      project_keys: 'OS,PMD',
      teams: undefined,
      tab: 'stack',
      search: undefined,
      offset: String(2 * ROOTS_DEFAULT_PAGE_SIZE),
      limit: String(ROOTS_DEFAULT_PAGE_SIZE),
      sort: undefined,
      hidden_statuses: undefined,
      only_moved: undefined,
    });
  });

  it('отбор и сортировка уходят на сервер — считаются по всей очереди', () => {
    const q = buildRootsQuery({
      ...base,
      sort: { field: 'status_changed_at', order: 'descend' },
      hiddenStatuses: ['Отменено', 'Готово'],
      onlyMoved: true,
    });
    expect(q.sort).toBe('-status_changed_at');
    // Порядок выбора статусов не плодит разные запросы.
    expect(q.hidden_statuses).toBe('Готово,Отменено');
    expect(q.only_moved).toBe('true');
    expect(buildRootsQuery({ ...base, sort: { field: 'goals', order: 'ascend' } }).sort).toBe('goals');
  });

  it('«Только переехавшие» действует только в «К разбору»', () => {
    expect(buildRootsQuery({ ...base, tab: 'active', onlyMoved: true }).only_moved).toBeUndefined();
  });
});

describe('разбор задач: листание', () => {
  it('номер страницы по сдвигу с сервера', () => {
    expect(pageOfOffset(0, 100)).toBe(1);
    expect(pageOfOffset(200, 100)).toBe(3);
  });

  it('после разбора последней страницы остаёмся на последней непустой', () => {
    expect(clampPage(5, 100, 401)).toBe(5);
    expect(clampPage(5, 100, 400)).toBe(4);
    expect(clampPage(3, 100, 0)).toBe(1);
  });
});

describe('разбор задач: порядок подзадач как у колонок', () => {
  const rows = [
    { key: 'A-1', status_changed_at: '2026-03-01T00:00:00', goals: 'Б' },
    { key: 'A-2', status_changed_at: null, goals: null },
    { key: 'A-3', status_changed_at: '2025-01-01T00:00:00', goals: 'а' },
  ];

  it('без сортировки — как пришло с сервера', () => {
    expect(sortRows(rows, null)).toBe(rows);
  });

  it('по дате смены статуса: без даты — раньше всех', () => {
    expect(sortRows(rows, { field: 'status_changed_at', order: 'ascend' }).map((r) => r.key))
      .toEqual(['A-2', 'A-3', 'A-1']);
    expect(sortRows(rows, { field: 'status_changed_at', order: 'descend' }).map((r) => r.key))
      .toEqual(['A-1', 'A-3', 'A-2']);
  });

  it('по целям', () => {
    expect(sortRows(rows, { field: 'goals', order: 'ascend' }).map((r) => r.key))
      .toEqual(['A-2', 'A-3', 'A-1']);
  });
});
