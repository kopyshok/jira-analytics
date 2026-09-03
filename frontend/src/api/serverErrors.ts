import { api } from './client';

export interface ServerErrorItem {
  id: string;
  at: string;
  method: string;
  path: string;
  query: string;
  error_type: string;
  message: string;
  traceback: string;
  user: string | null;
}

export interface ServerErrorList {
  started_at: string;
  capacity: number;
  items: ServerErrorItem[];
}

export const serverErrorsApi = {
  list: () => api.get<ServerErrorList>('/admin/errors'),
  clear: () => api.del<void>('/admin/errors'),
};
