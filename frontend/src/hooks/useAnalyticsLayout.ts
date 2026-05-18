import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchAnalyticsLayout,
  saveAnalyticsLayout,
  type AnalyticsLayout,
  type AnalyticsLevel,
} from '../api/analyticsReport';

export type { AnalyticsLevel };

export const DEFAULT_LAYOUT: Required<Pick<AnalyticsLayout, 'group_order' | 'hidden_levels'>> = {
  group_order: ['team', 'role', 'employee', 'work_type', 'category', 'issue'],
  hidden_levels: [],
};

export const ALL_LEVELS: AnalyticsLevel[] = ['team', 'role', 'employee', 'work_type', 'category', 'issue'];

export const LEVEL_LABELS: Record<AnalyticsLevel, string> = {
  team: 'Команда',
  role: 'Роль',
  employee: 'Сотрудник',
  work_type: 'Вид работ',
  category: 'Категория',
  issue: 'Задача',
};

export interface ResolvedLayout {
  visibleLevels: AnalyticsLevel[];
  hiddenLevels: AnalyticsLevel[];
  activePreset?: string;
}

export function resolveLayout(layout: AnalyticsLayout | undefined): ResolvedLayout {
  const order =
    layout?.group_order && layout.group_order.length > 0
      ? layout.group_order
      : DEFAULT_LAYOUT.group_order;
  const hidden = new Set(layout?.hidden_levels ?? []);
  hidden.delete('issue'); // issue is always visible
  const visibleLevels = order.filter((l) => !hidden.has(l));
  // Always ensure 'issue' is the last visible level
  if (!visibleLevels.includes('issue')) visibleLevels.push('issue');
  return {
    visibleLevels,
    hiddenLevels: Array.from(hidden),
    activePreset: layout?.active_preset,
  };
}

export function useAnalyticsLayout() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['analytics-layout'],
    queryFn: fetchAnalyticsLayout,
    staleTime: 5 * 60_000,
  });
  const mutate = useMutation({
    mutationFn: saveAnalyticsLayout,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['analytics-layout'] }),
  });
  const resolved = resolveLayout(query.data);
  return {
    layout: query.data ?? {},
    resolved,
    isLoading: query.isLoading,
    save: mutate.mutateAsync,
    isSaving: mutate.isPending,
  };
}
