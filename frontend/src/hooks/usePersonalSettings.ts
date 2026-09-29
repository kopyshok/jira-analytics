import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { PersonalSetting, PersonalSettingInput } from '../types/api';

const KEY = 'personal-settings';

export function usePersonalSettings(team: string | null | undefined) {
  return useQuery({
    queryKey: [KEY, team ?? null],
    queryFn: () =>
      api.get<PersonalSetting[]>('/planning/personal-settings', team ? { team } : undefined),
    enabled: !!team,
  });
}

/**
 * Записи, изменённые CRUD-мутациями, читаются и в раскладке, и в сценарии, и в
 * уже открытом расчёте фаз ресурсного плана — сбрасываем всё разом.
 */
function invalidatePersonalSettings(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: [KEY] });
  qc.invalidateQueries({ queryKey: ['planning', 'scenario'] });
  qc.invalidateQueries({ queryKey: ['gantt'] });
  qc.invalidateQueries({ queryKey: ['assignment-explain'] });
  qc.invalidateQueries({ queryKey: ['capacity-diff'] });
}

export function useCreatePersonalSetting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PersonalSettingInput) =>
      api.post<PersonalSetting>('/planning/personal-settings', body),
    onSuccess: () => invalidatePersonalSettings(qc),
  });
}

export function useUpdatePersonalSetting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: PersonalSettingInput }) =>
      api.put<PersonalSetting>(`/planning/personal-settings/${id}`, body),
    onSuccess: () => invalidatePersonalSettings(qc),
  });
}

export function useDeletePersonalSetting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del(`/planning/personal-settings/${id}`),
    onSuccess: () => invalidatePersonalSettings(qc),
  });
}
