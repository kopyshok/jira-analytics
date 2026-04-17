import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listHierarchyRules,
  createHierarchyRule,
  updateHierarchyRule,
  deleteHierarchyRule,
  reorderHierarchyRules,
} from '../api/hierarchyRules';
import type { HierarchyRuleCreate, HierarchyRuleUpdate } from '../types/api';

const QK = ['hierarchy-rules'] as const;

export const useHierarchyRules = () =>
  useQuery({ queryKey: QK, queryFn: listHierarchyRules });

export const useCreateHierarchyRule = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: HierarchyRuleCreate) => createHierarchyRule(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK });
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
    },
  });
};

export const useUpdateHierarchyRule = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: HierarchyRuleUpdate }) =>
      updateHierarchyRule(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK });
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
    },
  });
};

export const useDeleteHierarchyRule = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteHierarchyRule(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK });
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
    },
  });
};

export const useReorderHierarchyRules = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => reorderHierarchyRules(ids),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK });
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
    },
  });
};
