import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { api } from '../api/client';
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
  patchAllocationAssignee,
  reorderAllocations,
  getScenarioResource,
  getScenarioRules,
  putScenarioRules,
} from '../api/planning';
import type { AllocationResponse, ScenarioResponse, ScenarioRuleOut, ScenarioRuleInput, ResourceSummaryOut } from '../types/api';

export const useScenarios = (year?: string, quarter?: string, status?: 'draft' | 'approved', teams?: string) =>
  useQuery({
    queryKey: ['planning', 'scenarios', year, quarter, status, teams],
    queryFn: () => getScenarios(year, quarter, status, teams),
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

export const useScenarioResource = (sid?: string, enabled = true) =>
  useQuery({
    queryKey: ['planning', 'scenario', sid, 'resource'],
    queryFn: () => getScenarioResource(sid!),
    enabled: !!sid && enabled,
    staleTime: 60_000,
  });

export function useScenarioResourceSummary(
  scenarioId: string | undefined,
  enabled = true,
) {
  return useQuery({
    // Ключ под зонтиком ['planning', 'scenario', id, ...]: любая мутация,
    // инвалидирующая сценарий (useUpdateScenario, useSyncScenarioBacklog,
    // useApproveScenario и т.д.), автоматически обновит и эту сводку.
    // Раньше был отдельный корень ['scenario-resource-summary', id] —
    // изменение external_qa_hours через ExternalQaInput не обновляло верхнюю
    // таблицу, приходилось перезагружать страницу.
    queryKey: ['planning', 'scenario', scenarioId, 'summary'],
    queryFn: () =>
      api.get<ResourceSummaryOut>(`/planning/scenarios/${scenarioId}/resource-summary`),
    enabled: enabled && !!scenarioId,
    staleTime: 30_000,
  });
}

export function useCopyRulesFromTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      scenarioId,
      year,
      quarter,
    }: {
      scenarioId: string;
      year: number;
      quarter: number;
    }) =>
      api.post(
        `/planning/scenarios/${scenarioId}/copy-rules-from-template?year=${year}&quarter=${quarter}`,
        {},
      ),
    onSuccess: (_data, { scenarioId }) => {
      qc.invalidateQueries({ queryKey: ['planning', 'scenario', scenarioId] });
    },
  });
}

export const useScenarioRules = (sid?: string) =>
  useQuery({
    queryKey: ['planning', 'scenario', sid, 'rules'],
    queryFn: () => getScenarioRules(sid!),
    enabled: !!sid,
    staleTime: 60_000,
  });

export const usePutScenarioRules = () => {
  const qc = useQueryClient();
  const { notification } = App.useApp();
  return useMutation<ScenarioRuleOut[], Error, { scenarioId: string; rules: ScenarioRuleInput[] }>({
    mutationFn: ({ scenarioId, rules }) => putScenarioRules(scenarioId, rules),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['planning', 'scenario', vars.scenarioId] });
      notification.success({ title: 'Правила сохранены' });
    },
    onError: (err) => {
      notification.error({ title: 'Не удалось сохранить правила', description: err.message });
    },
  });
};

export const useReorderAllocations = () => {
  const qc = useQueryClient();
  const { notification } = App.useApp();
  return useMutation<
    AllocationResponse[],
    Error,
    { scenarioId: string; orderedIds: string[] },
    { prev?: AllocationResponse[] }
  >({
    mutationFn: ({ scenarioId, orderedIds }) => reorderAllocations(scenarioId, orderedIds),
    onMutate: async ({ scenarioId, orderedIds }) => {
      const key = ['planning', 'allocations', scenarioId];
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<AllocationResponse[]>(key);
      if (prev) {
        const byId = new Map(prev.map((a) => [a.id, a]));
        const reordered: AllocationResponse[] = [];
        orderedIds.forEach((id) => {
          const a = byId.get(id);
          if (a) {
            reordered.push(a);
            byId.delete(id);
          }
        });
        // Не упомянутые — в конец, сохраняя относительный порядок.
        byId.forEach((a) => reordered.push(a));
        qc.setQueryData<AllocationResponse[]>(key, reordered);
      }
      return { prev };
    },
    onError: (_err, vars, ctx) => {
      if (ctx?.prev) {
        qc.setQueryData(['planning', 'allocations', vars.scenarioId], ctx.prev);
      }
      notification.error({ title: 'Не удалось изменить порядок' });
    },
    onSettled: (_data, _err, vars) => {
      qc.invalidateQueries({ queryKey: ['planning', 'allocations', vars.scenarioId] });
    },
  });
};

export const usePatchAllocationAssignee = () => {
  const qc = useQueryClient();
  const { notification } = App.useApp();
  return useMutation<
    AllocationResponse,
    Error,
    { scenarioId: string; allocId: string; assigneeEmployeeId: string | null }
  >({
    mutationFn: ({ scenarioId, allocId, assigneeEmployeeId }) =>
      patchAllocationAssignee(scenarioId, allocId, assigneeEmployeeId),
    onSuccess: (_res, vars) => {
      qc.invalidateQueries({ queryKey: ['planning', 'allocations', vars.scenarioId] });
    },
    onError: () => {
      notification.error({ title: 'Не удалось сменить исполнителя' });
    },
  });
};

