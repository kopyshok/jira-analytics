import { api } from './client';
import type {
  ThemeListResponse,
  ThemeOut,
  ThemeCreateRequest,
  ThemeUpdateRequest,
  ThemeMergeRequest,
} from '../types/workTypeReport';

export const themesApi = {
  list: (
    workTypeId: string,
    includeArchived = false,
    signal?: AbortSignal,
  ) =>
    api.get<ThemeListResponse>(
      '/themes',
      { work_type_id: workTypeId, include_archived: includeArchived ? 'true' : 'false' },
      signal,
    ),

  create: (body: ThemeCreateRequest) =>
    api.post<ThemeOut>('/themes', body),

  update: (themeId: string, body: ThemeUpdateRequest) =>
    api.patch<ThemeOut>(`/themes/${encodeURIComponent(themeId)}`, body),

  archive: (themeId: string) =>
    api.post<ThemeOut>(`/themes/${encodeURIComponent(themeId)}/archive`),

  restore: (themeId: string) =>
    api.post<ThemeOut>(`/themes/${encodeURIComponent(themeId)}/restore`),

  merge: (themeId: string, body: ThemeMergeRequest) =>
    api.post<ThemeOut>(`/themes/${encodeURIComponent(themeId)}/merge`, body),
};
