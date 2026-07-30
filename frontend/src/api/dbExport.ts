import { api } from './client';

export interface DbExportStatus {
  state: 'idle' | 'running' | 'done' | 'error';
  tables_total: number;
  tables_done: number;
  current_table: string | null;
  rows_copied: number;
  error: string | null;
  file_name: string | null;
  file_size: number | null;
  local_password: string | null;
  revision: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export const dbExportApi = {
  status: () => api.get<DbExportStatus>('/admin/db-export'),
  start: () => api.post<DbExportStatus>('/admin/db-export', {}),
  download: (fileName: string) =>
    api.download('/admin/db-export/download', undefined, fileName),
};
