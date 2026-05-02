import { api } from './client';
import type { ProjectResponse } from '../types/api';
import type { ProjectListItem, ProjectDetail, ProjectSummary } from '../types/projects';

// Существующий — Jira projects list
export const getProjects = () => api.get<ProjectResponse[]>('/projects/all');

// Новые
export const projectsApi = {
  list: (
    params: { teams?: string; category?: string; status_category?: string; search?: string },
    signal?: AbortSignal,
  ) => api.get<ProjectListItem[]>('/projects', params as Record<string, string | undefined>, signal),

  detail: (key: string, signal?: AbortSignal) =>
    api.get<ProjectDetail>(`/projects/${encodeURIComponent(key)}`, undefined, signal),

  summary: (key: string, signal?: AbortSignal) =>
    api.get<ProjectSummary | null>(`/projects/${encodeURIComponent(key)}/summary`, undefined, signal),

  regenerateSummary: (key: string) =>
    api.post<ProjectSummary>(`/projects/${encodeURIComponent(key)}/regenerate-summary`),
};
