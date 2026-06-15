import { api } from './client';

export interface DeskEmployee {
  id: string;
  display_name: string;
  avatar_url: string | null;
}

export interface WorkDeskListItem {
  id: string;
  employee: DeskEmployee;
  status: string; // "active"
  token: string | null;
  enabled_widgets: string[];
  desk_url_path: string | null;
}

export interface WorkDeskCreated {
  id: string;
  token: string;
  employee_id: string;
  enabled_widgets: string[];
}

export const listWorkDesks = () => api.get<WorkDeskListItem[]>('/work-desks');

export const createWorkDesk = (body: { employee_id: string; enabled_widgets: string[] }) =>
  api.post<WorkDeskCreated>('/work-desks', body);

export const updateWorkDeskWidgets = (id: string, enabled_widgets: string[]) =>
  api.patch<WorkDeskCreated>(`/work-desks/${id}`, { enabled_widgets });

export const revokeWorkDesk = (id: string) =>
  api.post<{ status: string }>(`/work-desks/${id}/revoke`, {});

export const regenerateWorkDesk = (id: string) =>
  api.post<WorkDeskCreated>(`/work-desks/${id}/regenerate`, {});
