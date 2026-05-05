import { api } from './client';
import { pushError } from '../utils/errorStore';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';

export interface QualityMetric {
  plan_id: string;
  overload_days_pct: number;
  late_count: number;
  mean_utilization_pct: number;
  computed_at: string;
}

export interface OptimizeResult {
  new_plan_id: string;
  before: QualityMetric;
  after: QualityMetric;
  solver_status: 'OPTIMAL' | 'FEASIBLE' | 'INFEASIBLE';
  solve_time_ms: number;
  infeasible_items: string[];
}

export interface OptimizeProgress {
  type: 'progress';
  elapsed_ms: number;
}

type OptimizeEvent =
  | OptimizeProgress
  | (OptimizeResult & { type: 'done' })
  | { type: 'error'; detail: string; infeasible_items?: string[] }
  | { type: 'cancelled' };

export async function optimizeStream(
  planId: string,
  onProgress: (e: OptimizeProgress) => void,
  signal?: AbortSignal,
): Promise<OptimizeResult> {
  const url = `${BASE_URL}/resource-planning-v2/${planId}/optimize/stream`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { Accept: 'text/event-stream' },
      signal,
      credentials: 'include',
    });
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e;
    pushError({ ts: new Date().toISOString(), method: 'POST', url, status: null, detail: (e as Error).message });
    throw e;
  }
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail || res.statusText;
    pushError({ ts: new Date().toISOString(), method: 'POST', url, status: res.status, detail });
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let final: OptimizeResult | null = null;
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
        const payload = JSON.parse(line.slice(5).trim()) as OptimizeEvent;
        if (payload.type === 'progress') onProgress(payload);
        else if (payload.type === 'done') {
          const { type: _t, ...rest } = payload;
          void _t;
          final = rest as OptimizeResult;
        } else if (payload.type === 'error') throw new Error(payload.detail);
        else if (payload.type === 'cancelled') {
          const err = new Error('Optimization cancelled');
          err.name = 'AbortError';
          throw err;
        }
      }
    }
  }
  if (!final) throw new Error('Stream ended without done event');
  return final;
}

export const resourcePlanningV2Api = {
  quality: (planId: string, signal?: AbortSignal) =>
    api.get<QualityMetric>(`/resource-planning-v2/${planId}/quality`, undefined, signal),
  optimize: (planId: string) =>
    api.post<OptimizeResult>(`/resource-planning-v2/${planId}/optimize`),
};
