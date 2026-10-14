import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { jiraMigrationApi } from '../api/jiraMigration';
import type { DecisionBody, MigrationOverview } from '../api/jiraMigration';
import { pollInterval } from '../utils/jiraMigration';

export const MIGRATION_QUERY_KEY = ['admin', 'jira-migration'] as const;

/** Состояние переезда; пока идёт операция или синхронизация — обновляется само. */
export function useMigrationOverview() {
  return useQuery<MigrationOverview>({
    queryKey: MIGRATION_QUERY_KEY,
    queryFn: () => jiraMigrationApi.overview(),
    refetchInterval: (query) => pollInterval(query.state.data),
  });
}

function useInvalidateOverview() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: MIGRATION_QUERY_KEY });
}

export function useStartDryRun() {
  const invalidate = useInvalidateOverview();
  return useMutation({ mutationFn: () => jiraMigrationApi.startDryRun(), onSuccess: () => invalidate() });
}

export function useSetDecision() {
  const invalidate = useInvalidateOverview();
  return useMutation({
    mutationFn: (body: DecisionBody) => jiraMigrationApi.setDecision(body),
    onSuccess: () => invalidate(),
  });
}

export function useApplyMigration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (backupConfirmed: boolean) => jiraMigrationApi.apply(backupConfirmed),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MIGRATION_QUERY_KEY });
      qc.invalidateQueries({ queryKey: ['ui-config', 'jira-migration-state'] });
    },
  });
}

export function useRestartFullSync() {
  const invalidate = useInvalidateOverview();
  return useMutation({ mutationFn: () => jiraMigrationApi.restartFullSync(), onSuccess: () => invalidate() });
}

export function usePostCheck() {
  const invalidate = useInvalidateOverview();
  return useMutation({ mutationFn: () => jiraMigrationApi.postCheck(), onSuccess: () => invalidate() });
}

/** Поиск пользователя новой Jira для ручной привязки (от двух букв). */
export function useDcUserSearch(query: string) {
  const q = query.trim();
  return useQuery({
    // Свой ключ, не вложенный в ключ состояния: обновление состояния не перезапрашивает новую Jira.
    queryKey: ['admin', 'jira-migration-dc-users', q],
    queryFn: () => jiraMigrationApi.searchUsers(q),
    enabled: q.length >= 2,
    staleTime: 60_000,
  });
}
