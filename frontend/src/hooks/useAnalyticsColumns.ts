import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';

const ALL_COLUMNS = [
  'plan_hours', 'pct_plan', 'pct_in_group', 'pct_total', 'worklog_count', 'issue_count',
  'employee_count', 'avg_worklog_minutes',
  'status', 'issue_type', 'category', 'last_worklog_at', 'assignee_name',
];

// New users see pct_in_group by default; pct_total is opt-in.
// Existing users' saved column lists are unaffected.
const DEFAULT_VISIBLE = [
  'plan_hours', 'pct_plan', 'pct_in_group', 'worklog_count', 'issue_count',
  'employee_count', 'avg_worklog_minutes',
];

/**
 * Столбцы отчёта, которые включаются галочками в «Настройке отчёта».
 * Ключ — тот же, что в списке видимых столбцов пользователя и у столбца таблицы
 * отчёта (AnalyticsTable): расхождение ключей прячет столбец при любой галочке.
 */
export const CONFIGURABLE_COLUMN_LABELS: Record<string, string> = {
  plan_hours: 'Часы план',
  pct_plan: '% план',
  pct_in_group: '% в группе',
  pct_total: '% от итога',
  worklog_count: 'Ворклогов',
  issue_count: 'Задач',
  employee_count: 'Сотрудников',
  avg_worklog_minutes: 'Ср. минут',
};

export function useAnalyticsColumns() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['analytics-columns'],
    queryFn: () => api.get<{ columns: string[] }>('/users/me/analytics-columns'),
  });
  const visible = data?.columns?.length ? data.columns : DEFAULT_VISIBLE;

  const setMutation = useMutation({
    mutationFn: (cols: string[]) => api.put('/users/me/analytics-columns', { columns: cols }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['analytics-columns'] }),
  });

  return { visible, allColumns: ALL_COLUMNS, isLoading, setVisible: setMutation.mutate };
}
