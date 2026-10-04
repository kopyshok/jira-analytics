import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { fetchDeskWidget } from '../../api/desk';
import { useDeskPeriod } from './deskPeriod';

/** Запрос данных одного виджета стола с авто-обновлением раз в минуту.
 *  Квартал берётся из контекста стола и входит в ключ запроса. */
export function useDeskWidget<T>(token: string, key: string) {
  const period = useDeskPeriod();
  return useQuery({
    queryKey: ['desk', token, key, period?.year ?? null, period?.quarter ?? null],
    queryFn: ({ signal }) => fetchDeskWidget<T>(token, key, period, signal),
    refetchInterval: 60_000,
    retry: 1,
    placeholderData: keepPreviousData,
  });
}
