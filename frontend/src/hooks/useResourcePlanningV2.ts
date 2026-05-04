import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { resourcePlanningV2Api } from '../api/resourcePlanningV2';

export function usePlanQuality(planId: string | null) {
  return useQuery({
    queryKey: ['plan-quality', planId],
    queryFn: ({ signal }) => resourcePlanningV2Api.quality(planId!, signal),
    enabled: !!planId,
    staleTime: 30_000,
  });
}

export function useOptimizePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => resourcePlanningV2Api.optimize(planId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['resource-plans'] });
      qc.invalidateQueries({ queryKey: ['gantt-projection'] });
    },
  });
}
