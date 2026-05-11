import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { themesApi } from '../api/themes';
import type {
  ThemeCreateRequest,
  ThemeUpdateRequest,
  ThemeMergeRequest,
} from '../types/workTypeReport';

function themeListKey(workTypeId: string, includeArchived: boolean) {
  return ['theme-list', workTypeId, includeArchived] as const;
}

function invalidateThemes(
  qc: ReturnType<typeof useQueryClient>,
  workTypeId?: string,
) {
  qc.invalidateQueries({ queryKey: ['theme-list'] });
  if (workTypeId) {
    qc.invalidateQueries({ queryKey: ['work-type-report', workTypeId] });
  } else {
    qc.invalidateQueries({ queryKey: ['work-type-report'] });
  }
}

export function useThemeList(workTypeId: string | null, includeArchived = false) {
  return useQuery({
    queryKey: themeListKey(workTypeId ?? '', includeArchived),
    queryFn: ({ signal }) => themesApi.list(workTypeId!, includeArchived, signal),
    enabled: !!workTypeId,
    staleTime: 30_000,
  });
}

export function useCreateTheme() {
  const qc = useQueryClient();
  const { message } = App.useApp();
  return useMutation({
    mutationFn: (body: ThemeCreateRequest) => themesApi.create(body),
    onSuccess: (_data, vars) => {
      invalidateThemes(qc, vars.work_type_id);
      message.success('Тема создана');
    },
    onError: (e: unknown) => {
      const err = e as { message?: string };
      message.error(`Не удалось создать тему: ${err?.message ?? 'Ошибка'}`);
    },
  });
}

export function useUpdateTheme() {
  const qc = useQueryClient();
  const { message } = App.useApp();
  return useMutation({
    mutationFn: ({ themeId, body }: { themeId: string; body: ThemeUpdateRequest }) =>
      themesApi.update(themeId, body),
    onSuccess: (data) => {
      invalidateThemes(qc, data.work_type_id);
      message.success('Тема обновлена');
    },
    onError: (e: unknown) => {
      const err = e as { message?: string };
      message.error(`Не удалось обновить тему: ${err?.message ?? 'Ошибка'}`);
    },
  });
}

export function useArchiveTheme() {
  const qc = useQueryClient();
  const { message } = App.useApp();
  return useMutation({
    mutationFn: (themeId: string) => themesApi.archive(themeId),
    onSuccess: (data) => {
      invalidateThemes(qc, data.work_type_id);
      message.success('Тема архивирована');
    },
    onError: (e: unknown) => {
      const err = e as { message?: string };
      message.error(`Не удалось архивировать тему: ${err?.message ?? 'Ошибка'}`);
    },
  });
}

export function useRestoreTheme() {
  const qc = useQueryClient();
  const { message } = App.useApp();
  return useMutation({
    mutationFn: (themeId: string) => themesApi.restore(themeId),
    onSuccess: (data) => {
      invalidateThemes(qc, data.work_type_id);
      message.success('Тема восстановлена');
    },
    onError: (e: unknown) => {
      const err = e as { message?: string };
      message.error(`Не удалось восстановить тему: ${err?.message ?? 'Ошибка'}`);
    },
  });
}

export function useMergeThemes() {
  const qc = useQueryClient();
  const { message } = App.useApp();
  return useMutation({
    mutationFn: ({ themeId, body }: { themeId: string; body: ThemeMergeRequest }) =>
      themesApi.merge(themeId, body),
    onSuccess: (data) => {
      invalidateThemes(qc, data.work_type_id);
      message.success('Темы объединены');
    },
    onError: (e: unknown) => {
      const err = e as { message?: string };
      message.error(`Не удалось объединить темы: ${err?.message ?? 'Ошибка'}`);
    },
  });
}
