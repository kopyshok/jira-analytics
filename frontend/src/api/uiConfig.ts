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
