import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getJiraSettings, saveJiraSettings, testJiraCredentials, saveGenericSetting, getGenericSetting,
  getConfluenceSettings, saveConfluenceSettings, testConfluenceConnection,
} from '../api/settings';
import { getJiraBaseUrl, getJiraMigrationState } from '../api/uiConfig';
import { jiraBrowseUrl } from '../utils/jiraLinks';

export function useJiraSettings() {
  return useQuery({
    queryKey: ['settings', 'jira'],
    queryFn: getJiraSettings,
  });
}

/** Базовый URL Jira для deep-link'ов — доступен всем залогиненным (не только админу). */
export function useJiraBaseUrl() {
  return useQuery({
    queryKey: ['ui-config', 'jira-base-url'],
    queryFn: getJiraBaseUrl,
    staleTime: 5 * 60_000,
  });
}

/** Функция «ключ задачи → ссылка в Jira» по адресу из настроек. */
export function useJiraBrowseUrl(): (issueKey: string | null | undefined) => string | null {
  const baseUrl = useJiraBaseUrl().data?.base_url;
  return (issueKey) => jiraBrowseUrl(baseUrl, issueKey);
}

export function useSaveJiraSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: saveJiraSettings,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'jira'] }),
  });
}

export function useTestJiraCredentials() {
  return useMutation({ mutationFn: testJiraCredentials });
}

export function useSaveGenericSetting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => saveGenericSetting(key, value),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['settings', 'generic', vars.key] });
    },
  });
}

export function useGenericSetting(key: string) {
  return useQuery({
    queryKey: ['settings', 'generic', key],
    queryFn: () => getGenericSetting(key),
  });
}

/** Состояние переезда на новую Jira: пока он не завершён, синхронизация остановлена. */
export function useJiraMigrationState() {
  return useQuery({
    queryKey: ['ui-config', 'jira-migration-state'],
    queryFn: getJiraMigrationState,
    staleTime: 60_000,
  });
}

/** Синхронизация с Jira остановлена до завершения переезда. */
export function useSyncBlocked(): boolean {
  return useJiraMigrationState().data?.sync_blocked ?? false;
}

export function useConfluenceSettings() {
  return useQuery({
    queryKey: ['settings', 'confluence'],
    queryFn: getConfluenceSettings,
  });
}

export function useSaveConfluenceSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: saveConfluenceSettings,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'confluence'] }),
  });
}

export function useTestConfluenceConnection() {
  return useMutation({ mutationFn: testConfluenceConnection });
}
