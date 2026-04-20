import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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
} from '../api/planning';
import type { CapacityPreviewRequest } from '../types/planning';

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
    mutationFn: ({ id, data }: { id: string; data: { name?: string } }) => updateScenario(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['planning'] }),
  });
};

export const useDeleteScenario = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteScenario,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['planning'] }),
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
  return useMutation({
    mutationFn: ({
      scenarioId, allocId, data,
    }: {
      scenarioId: string;
      allocId: string;
      data: { included?: boolean; planned_hours?: number };
    }) => patchAllocation(scenarioId, allocId, data),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['planning', 'allocations', vars.scenarioId] });
    },
  });
};

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
