import { api } from './client';
import type { BacklogItemResponse } from '../types/api';

export const getBacklogItems = (year?: string, quarter?: string, projectId?: string) =>
  api.get<BacklogItemResponse[]>('/backlog', { year, quarter, project_id: projectId });

export const createBacklogItem = (data: {
  title: string;
  project_id?: string;
  quarter?: string;
  year?: number;
  estimate_hours?: number;
  priority?: number;
}) => api.post<BacklogItemResponse>('/backlog', data);

export const updateBacklogItem = (id: string, data: Partial<{
  title: string;
  project_id: string;
  quarter: string;
  year: number;
  estimate_hours: number;
  priority: number;
}>) => api.patch<BacklogItemResponse>(`/backlog/${id}`, data);

export const deleteBacklogItem = (id: string) => api.del(`/backlog/${id}`);
