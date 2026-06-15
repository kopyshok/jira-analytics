import { useQuery } from '@tanstack/react-query';
import { fetchDeskWidget } from '../../api/desk';

/** Запрос данных одного виджета стола с авто-обновлением раз в минуту. */
export function useDeskWidget<T>(token: string, key: string) {
  return useQuery({
    queryKey: ['desk', token, key],
    queryFn: ({ signal }) => fetchDeskWidget<T>(token, key, signal),
    refetchInterval: 60_000,
    retry: 1,
  });
}
