import { useQuery } from '@tanstack/react-query';
import { aiStatusApi } from '../api/aiStatus';

/**
 * Глобальный AI-рубильник. Default optimistic enabled=true пока грузится —
 * иначе кнопки мигают «выключено» при каждом первом рендере.
 */
export function useAiEnabled(): { enabled: boolean; isLoading: boolean } {
  const { data, isLoading } = useQuery({
    queryKey: ['ai-status'],
    queryFn: () => aiStatusApi.get(),
    staleTime: 60_000,
  });
  return { enabled: data?.enabled ?? true, isLoading };
}
