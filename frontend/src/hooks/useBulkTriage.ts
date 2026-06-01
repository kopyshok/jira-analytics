import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  bulkPreview,
  bulkArchive,
  bulkAcceptSuggestions,
  bulkCascadeInherit,
} from '../api/issues';
import type { BulkFilter } from '../types/api';

function invalidateAfterBulkMutation(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
  qc.invalidateQueries({ queryKey: ['backlog'] });
  qc.invalidateQueries({ queryKey: ['planning'] });
  qc.invalidateQueries({ queryKey: ['analytics'] });
}

export function useBulkPreview() {
  return useMutation({
    mutationFn: ({ filters, limit }: { filters: BulkFilter; limit?: number }) =>
      bulkPreview(filters, limit),
  });
}

export function useBulkArchive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      filters,
      categoryCode,
    }: {
      filters: BulkFilter;
      categoryCode: 'archive' | 'archive_target';
    }) => bulkArchive(filters, categoryCode),
    onSuccess: () => invalidateAfterBulkMutation(qc),
  });
}

export function useBulkAcceptSuggestions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ filters }: { filters: BulkFilter }) => bulkAcceptSuggestions(filters),
    onSuccess: () => invalidateAfterBulkMutation(qc),
  });
}

export function useBulkCascadeInherit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ ancestorIds }: { ancestorIds: string[] }) => bulkCascadeInherit(ancestorIds),
    onSuccess: () => invalidateAfterBulkMutation(qc),
  });
}
