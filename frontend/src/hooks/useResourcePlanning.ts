import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  computeResourcePlan, createResourcePlan, createScheduledBlock,
  deleteResourcePlan, deleteScheduledBlock, getGanttProjection,
  getResourcePlans, getScheduledBlocks, updateScheduledBlock,
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
