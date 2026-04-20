import { useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listCategories, createCategory, updateCategory, deleteCategory } from '../api/categories';
import { CATEGORY_LABELS, CATEGORY_COLORS } from '../utils/constants';
import type { CategoryResponse } from '../types/api';

export function useCategories() {
  const query = useQuery({
    queryKey: ['categories'],
    queryFn: listCategories,
    staleTime: 60_000,
  });

  const items = useMemo<CategoryResponse[]>(() => query.data ?? [], [query.data]);

  const labels = useMemo<Record<string, string>>(() => {
    if (query.data && query.data.length > 0) {
      return Object.fromEntries(query.data.map(c => [c.code, c.label]));
    }
    return CATEGORY_LABELS;
  }, [query.data]);

  const colors = useMemo<Record<string, string>>(() => {
    if (query.data && query.data.length > 0) {
      return Object.fromEntries(
        query.data.filter(c => c.color).map(c => [c.code, c.color!]),
      );
    }
    return CATEGORY_COLORS;
  }, [query.data]);

  const options = useMemo(
    () => Object.entries(labels).map(([value, label]) => ({ value, label })),
    [labels],
  );

  return { ...query, items, labels, colors, options };
}

export function useCreateCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createCategory,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['categories'] }),
  });
}

export function useUpdateCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: {
      id: string;
      body: { label?: string; color?: string | null; sort_order?: number; work_type_id?: string | null };
    }) => updateCategory(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['categories'] }),
  });
}

export function useDeleteCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteCategory,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['categories'] }),
  });
}
