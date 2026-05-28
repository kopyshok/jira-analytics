import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  computeResourcePlan, createResourcePlan, createScheduledBlock,
  deleteResourcePlan, deleteScheduledBlock, getGanttProjection,
  getResourcePlans, getScheduledBlocks, updateScheduledBlock,
  patchAssignment, type AssignmentPatch,
  patchConflict, type ConflictOut,
  explainConflict, type ConflictExplainOut,
  explainAssignment, type AssignmentExplainResponseV2,
  forkPlan, getPlanDiff,
  getPlanQuality,
  createDependency, patchDependency, deleteDependency,
  type DependencyOut,
  bulkClearAssignments, type BulkClearMode,
} from '../api/resourcePlanning';
import { trackAction } from '../lib/usage/track';

export const useScheduledBlocks = (team?: string) =>
  useQuery({
    queryKey: ['scheduled-blocks', team],
    queryFn: () => getScheduledBlocks(team),
    staleTime: 30_000,
  });

export const useCreateScheduledBlock = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createScheduledBlock,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-blocks'] }),
  });
};

export const useUpdateScheduledBlock = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateScheduledBlock>[1] }) =>
      updateScheduledBlock(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-blocks'] }),
  });
};

export const useDeleteScheduledBlock = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteScheduledBlock,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-blocks'] }),
  });
};

export const useResourcePlans = (team?: string) =>
  useQuery({
    queryKey: ['resource-plans', team],
    queryFn: () => getResourcePlans(team),
    staleTime: 30_000,
  });

export const useCreateResourcePlan = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createResourcePlan,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['resource-plans'] }),
  });
};

export const useDeleteResourcePlan = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteResourcePlan,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['resource-plans'] }),
  });
};

export const useComputeResourcePlan = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: computeResourcePlan,
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ['resource-plans'] });
      qc.invalidateQueries({ queryKey: ['gantt', id] });
    },
  });
};

export const useGanttProjection = (planId: string | null) =>
  useQuery({
    queryKey: ['gantt', planId],
    queryFn: () => getGanttProjection(planId!),
    enabled: !!planId,
    staleTime: 60_000,
  });

export function usePatchConflict(planId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ conflictId, status }: { conflictId: string; status: ConflictOut['status'] }) =>
      patchConflict(planId!, conflictId, status),
    onSuccess: () => {
      if (planId) qc.invalidateQueries({ queryKey: ['gantt', planId] });
    },
  });
}

export function useBulkClear(planId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (mode: BulkClearMode) => {
      if (!planId) throw new Error('No plan selected');
      return bulkClearAssignments(planId, mode);
    },
    onSuccess: () => {
      if (!planId) return;
      qc.invalidateQueries({ queryKey: ['gantt', planId] });
    },
  });
}

export function useExplainConflict(planId: string | null, conflictId: string | null, enabled: boolean) {
  return useQuery<ConflictExplainOut>({
    queryKey: ['conflict-explain', planId, conflictId],
    queryFn: () => explainConflict(planId!, conflictId!),
    enabled: !!planId && !!conflictId && enabled,
    staleTime: 30_000,
  });
}

export function useExplainAssignment(planId: string | null, assignmentId: string | null, enabled: boolean) {
  return useQuery<AssignmentExplainResponseV2>({
    queryKey: ['assignment-explain', planId, assignmentId],
    queryFn: () => explainAssignment(planId!, assignmentId!),
    enabled: !!planId && !!assignmentId && enabled,
    staleTime: 30_000,
  });
}

export function usePatchAssignment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      planId,
      assignmentId,
      data,
    }: {
      planId: string;
      assignmentId: string;
      data: AssignmentPatch;
    }) => patchAssignment(planId, assignmentId, data),
    onSuccess: (_, { planId, assignmentId }) => {
      qc.invalidateQueries({ queryKey: ['gantt', planId] });
      qc.invalidateQueries({ queryKey: ['resource-plans'] });
      trackAction('resource_plan_edited', assignmentId);
    },
  });
}

export function useForkPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ planId, label }: { planId: string; label?: string }) =>
      forkPlan(planId, label),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['resource-plans'] }),
  });
}

export function usePlanDiff(scenarioId: string | null, baselineId: string | null) {
  return useQuery({
    queryKey: ['plan-diff', scenarioId, baselineId],
    queryFn: () => getPlanDiff(scenarioId!, baselineId!),
    enabled: !!scenarioId && !!baselineId,
    staleTime: 30_000,
  });
}

export function usePlanQuality(planId: string | null) {
  return useQuery({
    queryKey: ['plan-quality', planId],
    queryFn: ({ signal }) => getPlanQuality(planId!, signal),
    enabled: !!planId,
    staleTime: 30_000,
  });
}

export function useCreateDependency() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      planId, fromItemId, toItemId, depType, lagDays,
    }: {
      planId: string;
      fromItemId: string;
      toItemId: string;
      depType?: DependencyOut['dep_type'];
      lagDays?: number;
    }) => createDependency(planId, {
      from_item_id: fromItemId,
      to_item_id: toItemId,
      dep_type: depType,
      lag_days: lagDays,
    }),
    onSuccess: (_, { planId }) => {
      qc.invalidateQueries({ queryKey: ['gantt', planId] });
    },
  });
}

export function usePatchDependency() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      planId, depId, data,
    }: {
      planId: string;
      depId: string;
      data: { dep_type?: DependencyOut['dep_type']; lag_days?: number };
    }) => patchDependency(planId, depId, data),
    onSuccess: (_, { planId }) => {
      qc.invalidateQueries({ queryKey: ['gantt', planId] });
    },
  });
}

export function useDeleteDependency() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ planId, depId }: { planId: string; depId: string }) =>
      deleteDependency(planId, depId),
    onSuccess: (_, { planId }) => {
      qc.invalidateQueries({ queryKey: ['gantt', planId] });
    },
  });
}
