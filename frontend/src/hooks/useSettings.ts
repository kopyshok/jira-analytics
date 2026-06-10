import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getJiraSettings, saveJiraSettings, testJiraCredentials, saveGenericSetting, getGenericSetting } from '../api/settings';
import { getJiraBaseUrl } from '../api/uiConfig';

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
