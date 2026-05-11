import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
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
  const { message } = App.useApp();
  return useMutation({
    mutationFn: (key: string) => projectsApi.regenerateSummary(key),
    onSuccess: (_data, key) => {
      qc.invalidateQueries({ queryKey: ['project-summary', key] });
      message.success('AI-резюме обновлено');
    },
    onError: (e: unknown) => {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      const detail = err?.response?.data?.detail ?? err?.message ?? 'Ошибка регенерации';
      message.error(`Регенерация не удалась: ${detail}`);
    },
  });
}
