import { api } from './client';
import type {
  BacklogItemResponse,
  BacklogImpactRisk,
  BacklogRefreshResult,
  BacklogView,
} from '../types/api';

export const getBacklogItems = (
  view: BacklogView = 'active',
  projectId?: string,
) =>
  api.get<BacklogItemResponse[]>('/backlog', { view, project_id: projectId });

export const createBacklogItem = (data: {
  title: string;
  project_id?: string;
  priority?: number;
  estimate_analyst_hours?: number;
  estimate_dev_hours?: number;
  estimate_qa_hours?: number;
  estimate_opo_hours?: number;
  opo_analyst_ratio?: number;
  impact?: BacklogImpactRisk;
  risk?: BacklogImpactRisk;
}) => api.post<BacklogItemResponse>('/backlog', data);

export const updateBacklogItem = (id: string, data: Partial<{
  title: string;
  project_id: string;
  priority: number;
  estimate_analyst_hours: number;
  estimate_dev_hours: number;
  estimate_qa_hours: number;
  estimate_opo_hours: number;
  opo_analyst_ratio: number;
  impact: BacklogImpactRisk;
  risk: BacklogImpactRisk;
}>) => api.patch<BacklogItemResponse>(`/backlog/${id}`, data);

export interface DeleteBacklogResult {
  status: string;
  id: string;
  allocations_removed: number;
  affected_scenarios: { id: string; name: string }[];
}

export const deleteBacklogItem = (id: string) =>
  api.del<DeleteBacklogResult>(`/backlog/${id}`);

export const linkJira = (id: string, jira_key: string) =>
  api.post<BacklogItemResponse>(`/backlog/${id}/link-jira`, { jira_key });

export const unlinkJira = (id: string) =>
  api.post<BacklogItemResponse>(`/backlog/${id}/unlink-jira`);

export const refreshFromJira = () =>
  api.post<BacklogRefreshResult>(`/backlog/refresh-from-jira`);

export const archiveBacklogItem = (id: string) =>
  api.post<BacklogItemResponse>(`/backlog/${id}/archive`);

export const restoreBacklogItem = (id: string) =>
  api.post<BacklogItemResponse>(`/backlog/${id}/restore`);
