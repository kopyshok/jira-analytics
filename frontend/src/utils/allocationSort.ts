/** Сортировка строк сценария по ФИО аналитика / разработчика — только для просмотра. */
export type PersonSortKey = 'analyst' | 'developer';
export type PersonSort = { key: PersonSortKey; dir: 'asc' | 'desc' };

/** Щелчок по заголовку: А→Я, Я→А, выключено. Другой столбец начинает с А→Я. */
export function nextPersonSort(current: PersonSort | null, key: PersonSortKey): PersonSort | null {
  if (!current || current.key !== key) return { key, dir: 'asc' };
  return current.dir === 'asc' ? { key, dir: 'desc' } : null;
}

type WithPeople = { assignee_display_name: string | null; developer_display_name: string | null };

const collator = new Intl.Collator('ru', { sensitivity: 'base' });

/** Пустые имена всегда в конце, при равных ФИО сохраняется исходный порядок. */
export function sortByPerson<T extends WithPeople>(items: T[], sort: PersonSort | null): T[] {
  if (!sort) return items;
  const name = (a: T) =>
    (sort.key === 'analyst' ? a.assignee_display_name : a.developer_display_name)?.trim() ?? '';
  const sign = sort.dir === 'asc' ? 1 : -1;
  return items
    .map((item, index) => ({ item, index, n: name(item) }))
    .sort((x, y) => {
      if (!x.n && !y.n) return x.index - y.index;
      if (!x.n) return 1;
      if (!y.n) return -1;
      return sign * collator.compare(x.n, y.n) || x.index - y.index;
    })
    .map((e) => e.item);
}
