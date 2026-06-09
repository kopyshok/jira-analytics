import { api } from './client';
import type { PipelineMode } from './syncRuns';

export type SyncScheduleOut = {
  id: string;
  name: string;
  cron_expr: string;
  mode: PipelineMode;
  team: string | null;
  enabled: boolean;
  last_run_id: string | null;
  next_run_at: string | null;
  description: string;
};

export type SchedulePreviewResponse = {
  valid: boolean;
  description: string | null;
  next_runs: string[];
  error: string | null;
};

export type SyncScheduleCreate = {
  name: string;
  cron_expr: string;
  mode: PipelineMode;
  team?: string;
  enabled?: boolean;
};

export type SyncScheduleUpdate = {
  cron_expr?: string;
  mode?: PipelineMode;
  team?: string | null;
  enabled?: boolean;
};

export const getSchedules = () =>
  api.get<SyncScheduleOut[]>('/sync/schedule');

export const createSchedule = (body: SyncScheduleCreate) =>
  api.post<SyncScheduleOut>('/sync/schedule', body);

export const updateSchedule = (id: string, body: SyncScheduleUpdate) =>
  api.patch<SyncScheduleOut>(`/sync/schedule/${id}`, body);

export const deleteSchedule = (id: string) =>
  api.del<void>(`/sync/schedule/${id}`);

export const runScheduleNow = (id: string) =>
  api.post<void>(`/sync/schedule/${id}/run-now`);

export const previewSchedule = (cron_expr: string) =>
  api.post<SchedulePreviewResponse>('/sync/schedule/preview', { cron_expr });
