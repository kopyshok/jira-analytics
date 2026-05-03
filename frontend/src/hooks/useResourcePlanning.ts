import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  computeResourcePlan, createResourcePlan, createScheduledBlock,
  deleteResourcePlan, deleteScheduledBlock, getGanttProjection,
  getResourcePlans, getScheduledBlocks, updateScheduledBlock,
  patchAssignment, type AssignmentPatch,
  patchConflict, type ConflictOut,
  forkPlan, getPlanDiff,
} from '../api/resourcePlanning';

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
    onSuccess: (_, { planId }) => {
      qc.invalidateQueries({ queryKey: ['gantt', planId] });
      qc.invalidateQueries({ queryKey: ['resource-plans'] });
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
