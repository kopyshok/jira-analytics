import { createContext, useContext } from 'react';

/** Выбранный квартал стола. */
export interface DeskPeriodValue {
  year: number;
  quarter: number;
}

/** Насколько далеко от текущего квартала можно листать (совпадает с бэкендом). */
export const MAX_QUARTER_SHIFT = 4;

/** Квартал, в котором находится указанная дата. */
export function quarterOf(d: Date): DeskPeriodValue {
  return { year: d.getFullYear(), quarter: Math.floor(d.getMonth() / 3) + 1 };
}

const index = (p: DeskPeriodValue) => p.year * 4 + p.quarter - 1;

/** Сдвиг квартала на delta кварталов (может быть отрицательным). */
export function shiftQuarter(p: DeskPeriodValue, delta: number): DeskPeriodValue {
  const i = index(p) + delta;
  return { year: Math.floor(i / 4), quarter: (i % 4) + 1 };
}

/** Насколько кварталов p отстоит от текущего (знак — направление). */
export function quarterOffset(p: DeskPeriodValue, current: DeskPeriodValue): number {
  return index(p) - index(current);
}

/** «2026-4» из адресной строки; мусор или выход за ±4 квартала → null (берётся текущий). */
export function parseQuarterParam(
  raw: string | null,
  current: DeskPeriodValue,
): DeskPeriodValue | null {
  const m = raw ? /^(\d{4})-([1-4])$/.exec(raw) : null;
  if (!m) return null;
  const p = { year: Number(m[1]), quarter: Number(m[2]) };
  return Math.abs(quarterOffset(p, current)) <= MAX_QUARTER_SHIFT ? p : null;
}

export function formatQuarterParam(p: DeskPeriodValue): string {
  return `${p.year}-${p.quarter}`;
}

/** Период, который виджеты кладут в запрос; null — «текущий», параметры не шлём. */
export const DeskPeriodContext = createContext<DeskPeriodValue | null>(null);

export function useDeskPeriod(): DeskPeriodValue | null {
  return useContext(DeskPeriodContext);
}
