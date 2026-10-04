import { api } from './client';
import type { DeskMeta } from '../types/desk';

/** Квартал для запросов стола; null — текущий (параметры не отправляются). */
type PeriodParam = { year: number; quarter: number } | null;

function periodParams(period: PeriodParam): Record<string, string> | undefined {
  return period ? { year: String(period.year), quarter: String(period.quarter) } : undefined;
}

/** Метаданные публичного рабочего стола по токену (без авторизации). */
export function fetchDeskMeta(
  token: string,
  period: PeriodParam = null,
  signal?: AbortSignal,
): Promise<DeskMeta> {
  return api.get<DeskMeta>(`/desk/${encodeURIComponent(token)}`, periodParams(period), signal);
}

/** Данные одного виджета стола. Тип конкретизируется на стороне виджета. */
export function fetchDeskWidget<T>(
  token: string,
  key: string,
  period: PeriodParam = null,
  signal?: AbortSignal,
): Promise<T> {
  return api.get<T>(
    `/desk/${encodeURIComponent(token)}/widget/${encodeURIComponent(key)}`,
    periodParams(period),
    signal,
  );
}
