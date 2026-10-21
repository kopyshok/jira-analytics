/**
 * Пункт бокового меню, к которому относится страница: сам адрес раздела или
 * самый длинный раздел, внутри которого лежит страница (сравнение сценариев
 * внутри ресурсного планирования, карточка проекта внутри проектов).
 * Главная подсвечивается только сама. Нет подходящего раздела — null.
 */
export function activeNavKey(pathname: string, keys: readonly string[]): string | null {
  let best: string | null = null;
  for (const key of keys) {
    const inside = key === '/'
      ? pathname === '/'
      : pathname === key || pathname.startsWith(`${key}/`);
    if (inside && (best === null || key.length > best.length)) best = key;
  }
  return best;
}
