import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { projectsApi } from '../api/projects';

export function useProjectSummary(key: string | null) {
  return useQuery({
    queryKey: ['project-summary', key],
    queryFn: ({ signal }) => projectsApi.summary(key!, signal),
    enabled: !!key,
    staleTime: 60_000,
  });
}

export function useRegenerateSummary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (key: string) => projectsApi.regenerateSummary(key),
    onSuccess: (_data, key) => {
      qc.invalidateQueries({ queryKey: ['project-summary', key] });
    },
  });
}
