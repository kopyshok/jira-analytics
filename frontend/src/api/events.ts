import { BASE_URL } from './client';

export type GlobalEvent =
  | { type: 'sync_started'; run_id: string; mode: string }
  | { type: 'stage_start'; stage: string; run_id: string }
  | { type: 'stage_done'; stage: string; run_id: string; counts: Record<string, number> }
  | { type: 'stage_failed'; stage: string; run_id: string; error: string }
  | { type: 'pipeline_done'; run_id: string; status: string }
  | { type: 'entity_changed'; entity: string };

/** URL глобального SSE-потока событий. */
export const EVENTS_STREAM_URL = `${BASE_URL}/events/stream`;
