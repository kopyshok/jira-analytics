import { api } from './client';

export type SyncRunStatus = 'running' | 'ok' | 'partial' | 'failed' | 'cancelled' | 'skipped';
export type PipelineMode = 'quick' | 'normal' | 'full' | 'team';
export type SyncTrigger = 'manual' | 'scheduled';

export type StageReport = {
  stage: string;
  started: string;
  finished: string | null;
  status: string;
  counts: Record<string, number>;
  error: string | null;
};

export type SyncRunOut = {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: SyncRunStatus;
  trigger: SyncTrigger;
  mode: PipelineMode;
  team: string | null;
  stages_json: StageReport[];
  error_text: string | null;
  schedule_id: string | null;
};

export const getSyncRuns = (limit = 20) =>
  api.get<SyncRunOut[]>('/sync/runs', { limit: String(limit) });

export const getSyncRun = (runId: string) =>
  api.get<SyncRunOut>(`/sync/runs/${runId}`);
