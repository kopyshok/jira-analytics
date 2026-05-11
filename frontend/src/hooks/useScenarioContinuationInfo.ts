import { useQuery } from '@tanstack/react-query';
import { getContinuationInfo } from '../api/planning';

export function useScenarioContinuationInfo(scenarioId: string | undefined) {
  return useQuery({
    queryKey: ['planning-continuation', scenarioId],
    queryFn: () => getContinuationInfo(scenarioId as string),
    enabled: !!scenarioId,
    staleTime: 30_000,
  });
}
