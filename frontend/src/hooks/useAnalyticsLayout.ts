import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchAnalyticsLayout,
  saveAnalyticsLayout,
  type AnalyticsLayout,
  type AnalyticsLevel,
} from '../api/analyticsReport';

export type { AnalyticsLevel };

export const DEFAULT_LAYOUT: Required<Pick<AnalyticsLayout, 'group_order' | 'hidden_levels'>> = {
  // Группа внутри команды по умолчанию скрыта: у команд без деления она даёт
  // единственную строку «Без группы» и только мешает.
  group_order: ['team', 'subgroup', 'role', 'employee', 'work_type', 'category', 'issue'],
  hidden_levels: ['subgroup'],
};

export const ALL_LEVELS: AnalyticsLevel[] = [
  'team',
  'subgroup',
  'role',
  'employee',
  'work_type',
  'category',
  'issue',
];

export const LEVEL_LABELS: Record<AnalyticsLevel, string> = {
  team: 'Команда',
  subgroup: 'Группа',
  role: 'Роль',
  employee: 'Сотрудник',
  work_type: 'Вид работ',
  category: 'Категория',
  issue: 'Задача',
};

/** Порядок пользователя + уровни, появившиеся позже него, в конец. */
export function withAllLevels(order: AnalyticsLevel[]): AnalyticsLevel[] {
  return [...order, ...ALL_LEVELS.filter((l) => !order.includes(l))];
}

export interface ResolvedLayout {
  visibleLevels: AnalyticsLevel[];
  hiddenLevels: AnalyticsLevel[];
  activePreset?: string;
  showFactBar: boolean;
}

export function resolveLayout(layout: AnalyticsLayout | undefined): ResolvedLayout {
  const saved =
    layout?.group_order && layout.group_order.length > 0
      ? layout.group_order
      : DEFAULT_LAYOUT.group_order;
  const order = withAllLevels(saved);
  const hidden = new Set(layout?.hidden_levels ?? []);
  // Уровень, которого в сохранённой раскладке ещё не было, показываем скрытым:
  // иначе обновление сервиса молча добавило бы всем новую группировку.
  for (const level of ALL_LEVELS) {
    if (!saved.includes(level)) hidden.add(level);
  }
  hidden.delete('issue'); // issue is always visible
  const visibleLevels = order.filter((l) => !hidden.has(l));
  // Always ensure 'issue' is the last visible level
  if (!visibleLevels.includes('issue')) visibleLevels.push('issue');
  return {
    visibleLevels,
    hiddenLevels: Array.from(hidden),
    activePreset: layout?.active_preset,
    showFactBar: layout?.show_fact_bar ?? true,
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
