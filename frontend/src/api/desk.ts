import { api } from './client';
import type { DeskMeta } from '../types/desk';

/** Метаданные публичного рабочего стола по токену (без авторизации). */
export function fetchDeskMeta(token: string, signal?: AbortSignal): Promise<DeskMeta> {
  return api.get<DeskMeta>(`/desk/${encodeURIComponent(token)}`, undefined, signal);
}

/** Данные одного виджета стола. Тип конкретизируется на стороне виджета. */
export function fetchDeskWidget<T>(token: string, key: string, signal?: AbortSignal): Promise<T> {
  return api.get<T>(
    `/desk/${encodeURIComponent(token)}/widget/${encodeURIComponent(key)}`,
    undefined,
    signal,
  );
}
