/**
 * Цвета данных обложки «Пульт» (тон индикаторов прибора).
 * Подставляются только вместо значений по умолчанию: свои цвета пользователя
 * из окна «Цвета» остаются как есть.
 */
export const PULT_PHASE_COLORS: Record<string, string> = {
  analyst: '#4DBFB4',
  dev: '#2F6FDE',
  qa: '#F0A04B',
  opo: '#8E5BC2',
};

/** Индикаторы статусов: у него / ждёт не его / не начата / закрыта / не распределён / ошибка. */
export const PULT_SIGNAL = {
  blue: '#2F6FDE',
  amber: '#D99A00',
  grey: '#9A978F',
  green: '#2E9E5B',
  violet: '#8E5BC2',
  red: '#D9381E',
} as const;

/** Загрузка дня (клетки «Загрузка сотрудников по дням»). */
export const PULT_LOAD = {
  free: '#FFFFFF',
  low: '#A9C8F0',
  mid: '#5F93DB',
  high: '#E3A92A',
  over: '#D9381E',
  weekend: '#E1DED7',
  holiday: '#9A978F',
  absence: '#2B2B29',
} as const;
