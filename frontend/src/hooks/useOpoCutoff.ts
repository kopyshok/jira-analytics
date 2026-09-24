import { useContext } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { GlobalPeriodContext } from './useGlobalPeriod';
import { isOpoOff } from '../utils/opo';

export const OPO_CUTOFF_KEY = 'planning_opo_cutoff';

/** Отсечка ОПЭ (общая настройка сервиса): «2026Q4» либо null — учитываем всегда. */
export function useOpoCutoff() {
  const { data } = useQuery({
    queryKey: [OPO_CUTOFF_KEY],
    // Не /settings: он только для администратора, остальным отвечает отказом.
    queryFn: () => api.get<{ key: string; value: string | null }>('/planning/opo-cutoff'),
    staleTime: 5 * 60 * 1000,
  });
  const cutoff = data?.value ?? null;
  // Экраны без собственного квартала (целевые задачи, справочники, модалки)
  // ориентируются на период, выбранный в шапке; вне провайдера — на текущий.
  const period = useContext(GlobalPeriodContext)?.period;
  const now = new Date();
  const year = period?.year ?? now.getFullYear();
  const quarter = period?.quarter ?? Math.floor(now.getMonth() / 3) + 1;
  return {
    cutoff,
    /** Выключен ли ОПЭ для конкретного квартала. */
    opoOffFor: (y: number | null | undefined, q: number | string | null | undefined) =>
      isOpoOff(cutoff, y, q),
    /** Выключен ли ОПЭ для выбранного в шапке квартала. */
    opoOffNow: isOpoOff(cutoff, year, quarter),
  };
}
