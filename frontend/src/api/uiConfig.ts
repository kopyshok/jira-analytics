import { api } from './client';

export interface HiddenSectionsResponse {
  keys: string[];
}

export const getHiddenSections = (): Promise<HiddenSectionsResponse> =>
  api.get<HiddenSectionsResponse>('/ui-config/hidden-sections');

export const putHiddenSections = (keys: string[]): Promise<HiddenSectionsResponse> =>
  api.put<HiddenSectionsResponse>('/ui-config/hidden-sections', { keys });

export interface JiraBaseUrlResponse {
  base_url: string | null;
}

export const getJiraBaseUrl = (): Promise<JiraBaseUrlResponse> =>
  api.get<JiraBaseUrlResponse>('/ui-config/jira-base-url');

export interface JiraMigrationStateResponse {
  state: 'pending' | 'done';
  sync_blocked: boolean;
}

export const getJiraMigrationState = (): Promise<JiraMigrationStateResponse> =>
  api.get<JiraMigrationStateResponse>('/ui-config/jira-migration-state');
