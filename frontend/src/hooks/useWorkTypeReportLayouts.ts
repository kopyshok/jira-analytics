import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import { workTypeReportApi } from '../api/workTypeReport';
import type { LayoutCreateRequest, LayoutUpdateRequest } from '../types/workTypeReport';

function layoutListKey(workTypeId: string) {
  return ['layout-list', workTypeId] as const;
}

export function useLayoutList(workTypeId: string | null) {
  return useQuery({
    queryKey: layoutListKey(workTypeId ?? ''),
    queryFn: ({ signal }) => workTypeReportApi.listLayouts(workTypeId!, signal),
    enabled: !!workTypeId,
    staleTime: 60_000,
  });
}

export function useCreateLayout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: LayoutCreateRequest) => workTypeReportApi.createLayout(body),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: layoutListKey(data.work_type_id) });
      message.success('Макет создан');
    },
    onError: (e: unknown) => {
      const err = e as { message?: string };
      message.error(`Не удалось создать макет: ${err?.message ?? 'Ошибка'}`);
    },
  });
}

export function useUpdateLayout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ layoutId, body }: { layoutId: string; body: LayoutUpdateRequest }) =>
      workTypeReportApi.updateLayout(layoutId, body),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: layoutListKey(data.work_type_id) });
      message.success('Макет обновлён');
    },
    onError: (e: unknown) => {
      const err = e as { message?: string };
      message.error(`Не удалось обновить макет: ${err?.message ?? 'Ошибка'}`);
    },
  });
}

export function useDeleteLayout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ layoutId, workTypeId }: { layoutId: string; workTypeId: string }) =>
      workTypeReportApi.deleteLayout(layoutId).then((r) => ({ ...r, workTypeId })),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: layoutListKey(data.workTypeId) });
      message.success('Макет удалён');
    },
    onError: (e: unknown) => {
      const err = e as { message?: string };
      message.error(`Не удалось удалить макет: ${err?.message ?? 'Ошибка'}`);
    },
  });
}
