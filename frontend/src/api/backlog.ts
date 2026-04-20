import { api } from './client';
import type {
  BacklogItemResponse,
  BacklogImpactRisk,
  BacklogRefreshResult,
} from '../types/api';

export const getBacklogItems = (year?: string, quarter?: string, projectId?: string) =>
  api.get<BacklogItemResponse[]>('/backlog', { year, quarter, project_id: projectId });

export const createBacklogItem = (data: {
  title: string;
  project_id?: string;
  quarter?: string;
  year?: number;
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
  quarter: string;
  year: number;
  priority: number;
  estimate_analyst_hours: number;
  estimate_dev_hours: number;
  estimate_qa_hours: number;
  estimate_opo_hours: number;
  opo_analyst_ratio: number;
  impact: BacklogImpactRisk;
  risk: BacklogImpactRisk;
}>) => api.patch<BacklogItemResponse>(`/backlog/${id}`, data);

export const deleteBacklogItem = (id: string) => api.del(`/backlog/${id}`);

export const linkJira = (id: string, jira_key: string) =>
  api.post<BacklogItemResponse>(`/backlog/${id}/link-jira`, { jira_key });

export const unlinkJira = (id: string) =>
  api.post<BacklogItemResponse>(`/backlog/${id}/unlink-jira`);

export const refreshFromJira = () =>
  api.post<BacklogRefreshResult>(`/backlog/refresh-from-jira`);
