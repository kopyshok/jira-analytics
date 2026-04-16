import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getJiraSettings, saveJiraSettings, testJiraCredentials, saveGenericSetting } from '../api/settings';

export function useJiraSettings() {
  return useQuery({
    queryKey: ['settings', 'jira'],
    queryFn: getJiraSettings,
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
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => saveGenericSetting(key, value),
  });
}
