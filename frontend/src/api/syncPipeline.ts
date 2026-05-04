import { BASE_URL } from './client';
import { pushError } from '../utils/errorStore';

export type PipelineMode = 'quick' | 'normal' | 'full' | 'team';

export type PipelineRequest = {
  mode: PipelineMode;
  team?: string;
  since?: string; // ISO date YYYY-MM-DD
};

export type PipelineEvent =
  | { type: 'sync_started'; run_id: string; mode: PipelineMode }
  | { type: 'stage_start'; stage: string; run_id: string }
  | { type: 'stage_done'; stage: string; run_id: string; counts: Record<string, number> }
  | { type: 'stage_failed'; stage: string; run_id: string; error: string }
  | { type: 'pipeline_done'; run_id: string; status: string }
  | { type: 'entity_changed'; entity: string };

/**
 * Запустить pipeline синхронизации. Возвращает SSE-поток событий.
 * onEvent вызывается на каждое событие. Финальное pipeline_done возвращается как Promise.
 */
export async function runPipelineStream(
  req: PipelineRequest,
  onEvent: (e: PipelineEvent) => void,
  signal?: AbortSignal,
): Promise<{ run_id: string; status: string }> {
  const url = `${BASE_URL}/sync/pipeline`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(req),
      signal,
      credentials: 'include',
    });
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e;
    pushError({
      ts: new Date().toISOString(), method: 'POST', url,
      status: null, detail: (e as Error).message,
      requestBody: JSON.stringify(req),
    });
    throw e;
  }

  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      const err = await res.json();
      detail = err.detail || detail;
    } catch { /* ignore */ }
    pushError({
      ts: new Date().toISOString(), method: 'POST', url,
      status: res.status, detail,
      requestBody: JSON.stringify(req),
    });
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let final: { run_id: string; status: string } | null = null;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep = buffer.indexOf('\n\n');
    while (sep !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      sep = buffer.indexOf('\n\n');
      for (const line of raw.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const text = line.slice(5).trim();
        if (!text) continue;
        try {
          const payload = JSON.parse(text) as PipelineEvent;
          onEvent(payload);
          if (payload.type === 'pipeline_done') {
            final = { run_id: payload.run_id, status: payload.status };
          }
        } catch { /* ignore malformed */ }
      }
    }
  }

  if (!final) throw new Error('Pipeline stream ended without pipeline_done event');
  return final;
}
