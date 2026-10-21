/**
 * Полоса слева у строки идеи в сценарии (встроенный стиль строки).
 *
 * Состояние строки — нет оценок, включено при дефиците, уже в работе — рисует
 * свою цветную полосу классом. Встроенный стиль перекрывает класс, поэтому
 * полосу «включено» задаём только строке без состояния: иначе цвет состояния
 * не виден.
 */
export function rowLeftBorder(included: boolean, rowStateClass: string): string | undefined {
  if (rowStateClass) return undefined;
  return included ? '3px solid var(--accent-1, #00c9c8)' : '3px solid transparent';
}
