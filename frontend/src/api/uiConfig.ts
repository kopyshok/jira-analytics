import { api } from './client';

export interface HiddenSectionsResponse {
  keys: string[];
}

export const getHiddenSections = (): Promise<HiddenSectionsResponse> =>
  api.get<HiddenSectionsResponse>('/ui-config/hidden-sections');

export const putHiddenSections = (keys: string[]): Promise<HiddenSectionsResponse> =>
  api.put<HiddenSectionsResponse>('/ui-config/hidden-sections', { keys });
