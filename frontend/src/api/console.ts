import { api } from './client';

export type ConsoleTarget = 'jira' | 'confluence';

export interface ConsoleRunBrief {
  id: string;
  created_at: string;
  user_name: string;
  target: ConsoleTarget;
  masked: boolean;
  first_line: string;
  request_count: number;
  error_count: number;
  rejected_count: number;
  duration_ms: number;
}

export interface ConsoleRun extends ConsoleRunBrief {
  input_text: string;
  output_text: string;
}

export const consoleApi = {
  run: (body: { target: ConsoleTarget; text: string; mask: boolean }) =>
    api.post<ConsoleRun>('/admin/console/run', body),
  list: () => api.get<{ items: ConsoleRunBrief[] }>('/admin/console/runs'),
  get: (id: string) => api.get<ConsoleRun>(`/admin/console/runs/${id}`),
  remove: (id: string) => api.del<void>(`/admin/console/runs/${id}`),
};
