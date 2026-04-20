import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import {
  getScenarios,
  getScenario,
  createScenario,
  updateScenario,
  deleteScenario,
  approveScenario,
  revertScenario,
  syncScenarioBacklog,
  getScenarioAllocations,
  patchAllocation,
  capacityPreview,
  getScenarioResource,
} from '../api/planning';
import type { CapacityPreviewRequest } from '../types/planning';
import type { AllocationResponse, ScenarioResponse } from '../types/api';

export const useScenarios = (year?: string, quarter?: string, status?: 'draft' | 'approved') =>
  useQuery({
    queryKey: ['planning', 'scenarios', year, quarter, status],
    queryFn: () => getScenarios(year, quarter, status),
  });

export const useScenario = (id: string | null) =>
  useQuery({
    queryKey: ['planning', 'scenario', id],
    queryFn: () => getScenario(id!),
    enabled: !!id,
  });

export const useCreateScenario = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createScenario,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['planning'] }),
  });
};

export const useUpdateScenario = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: { name?: string; team?: string | null; external_qa_hours?: number | null };
    }) => updateScenario(id, data),
    onSuccess: (_res, vars) => {
      qc.invalidateQueries({ queryKey: ['planning', 'scenario', vars.id] });
      qc.invalidateQueries({ queryKey: ['planning', 'scenario', vars.id, 'resource'] });
      qc.invalidateQueries({ queryKey: ['planning', 'scenarios'] });
    },
  });
};

export const useDeleteScenario = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteScenario,
    // onMutate (ДО запроса): отменяем in-flight запросы по сценарию и убираем
    // его из кэша списков. Без этого useScenario / useScenarioAllocations
    // успевают отловить 404 при refetch'е после invalidate.
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: ['planning', 'scenario', id] });
      await qc.cancelQueries({ queryKey: ['planning', 'allocations', id] });
      qc.setQueriesData<ScenarioResponse[]>(
        { queryKey: ['planning', 'scenarios'] },
        (old) => (old ? old.filter((s) => s.id !== id) : old),
      );
      qc.removeQueries({ queryKey: ['planning', 'scenario', id] });
      qc.removeQueries({ queryKey: ['planning', 'allocations', id] });
    },
    // onSuccess инвалидируем только список (не wildcard-planning), чтобы
    // не ресетать удалённый сценарий обратно через observer re-fetch.
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ['planning', 'scenarios'] }),
  });
};

export const useApproveScenario = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: approveScenario,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['planning'] }),
  });
};

export const useRevertScenario = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: revertScenario,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['planning'] }),
  });
};

export const useSyncScenarioBacklog = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: syncScenarioBacklog,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['planning'] }),
  });
};

export const useScenarioAllocations = (scenarioId: string | null) =>
  useQuery({
    queryKey: ['planning', 'allocations', scenarioId],
    queryFn: () => getScenarioAllocations(scenarioId!),
    enabled: !!scenarioId,
  });

export const usePatchAllocation = () => {
  const qc = useQueryClient();
  const { notification } = App.useApp();
  // NOTE: TanStack cancelQueries cancels running *queries*, not in-flight mutations.
  // Rapid-fire clicks may cause out-of-order server responses; acceptable for a
  // single-user app. The optimistic cache is always overwritten by onSettled invalidation.
  return useMutation<
    AllocationResponse,
    Error,
    { scenarioId: string; allocId: string; data: { included?: boolean; planned_hours?: number } },
    { prev?: AllocationResponse[] }
  >({
    mutationFn: ({ scenarioId, allocId, data }) => patchAllocation(scenarioId, allocId, data),
    onMutate: async ({ scenarioId, allocId, data }) => {
      const key = ['planning', 'allocations', scenarioId];
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<AllocationResponse[]>(key);
      if (prev && data.included !== undefined) {
        qc.setQueryData<AllocationResponse[]>(
          key,
          prev.map((a) => (a.id === allocId ? { ...a, included: data.included! } : a)),
        );
      }
      return { prev };
    },
    onError: (_err, vars, ctx) => {
      if (ctx?.prev) {
        qc.setQueryData(['planning', 'allocations', vars.scenarioId], ctx.prev);
      }
      notification.error({ title: 'Не удалось сохранить изменение' });
    },
    onSettled: (_data, _err, vars) => {
      // Синхронизируем кэш с сервером, чтобы получить актуальный planned_hours.
      // НЕ инвалидируем resource — ёмкость команды не меняется при переключении идеи.
      qc.invalidateQueries({ queryKey: ['planning', 'allocations', vars.scenarioId] });
    },
  });
};

export const useScenarioResource = (sid?: string) =>
  useQuery({
    queryKey: ['planning', 'scenario', sid, 'resource'],
    queryFn: () => getScenarioResource(sid!),
    enabled: !!sid,
    staleTime: 60_000,
  });

/** Live-расчёт ёмкости для страницы «Сценарии». Сервер принимает список
 *  backlog_item_ids (включённых в сценарий) и возвращает capacity/demand
 *  по ролям и разбивку по сотрудникам. */
export const useCapacityPreview = (req: CapacityPreviewRequest) =>
  useQuery({
    queryKey: ['planning', 'capacity-preview', req],
    queryFn: () => capacityPreview(req),
    staleTime: 10_000,
    enabled: !!req.year && !!req.quarter,
  });
