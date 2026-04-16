import { api } from './client';
import type { JiraSettingsResponse, JiraTestResponse } from '../types/api';

export const getJiraSettings = () =>
  api.get<JiraSettingsResponse>('/settings/jira');

export const saveJiraSettings = (body: { email?: string; api_token?: string; base_url?: string }) =>
  api.put<JiraSettingsResponse>('/settings/jira', body);

export const testJiraCredentials = (body: { email: string; api_token: string; base_url: string }) =>
  api.post<JiraTestResponse>('/settings/jira/test', body);

export const saveGenericSetting = (key: string, value: string) =>
  api.put<{ key: string; ok: boolean }>('/settings/generic', { key, value });
