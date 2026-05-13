import { api, BASE_URL } from './client';
import type {
  WorkTypeReportResponse,
  CandidateAcceptRequest,
  CandidateMergeRequest,
  CandidateIgnoreRequest,
  ManualClassifyRequest,
  LayoutOut,
  LayoutCreateRequest,
} from '../types/workTypeReport';

export type BuildEvent =
  | { type: 'phase_start'; phase: 'scope' | 'map' | 'cluster' | 'reduce' | 'save'; total?: number }
  | { type: 'progress'; phase: string; current: number; total: number; item_key?: string }
  | { type: 'phase_done'; phase: string; count?: number }
  | { type: 'done'; snapshot_id: string; work_type_id: string; year: number; quarter: number; month: number | null; totals: Record<string, unknown> }
  | { type: 'error'; detail: string }
  | { type: 'cancelled'; reason?: string };

export interface GetReportParams {
  work_type_id: string;
  year: number;
  quarter: number;
  month?: number | null;
  /** Array of team names; converted to CSV for the backend query param */
  teams?: string[];
}

export const workTypeReportApi = {
  /** GET — cached snapshot (builds on first call) */
  get: (params: GetReportParams, signal?: AbortSignal) => {
    const { work_type_id, year, quarter, month, teams } = params;
    const teamsCsv = teams && teams.length > 0 ? teams.join(',') : undefined;
    return api.get<WorkTypeReportResponse>(
      '/work-type-report',
      {
        work_type_id,
        year: String(year),
        quarter: String(quarter),
        month: month != null ? String(month) : undefined,
        teams: teamsCsv,
      },
      signal,
    );
  },

  /** POST — force-builds a new snapshot (force_refresh handled by caller via body) */
  build: (body: {
    work_type_id: string;
    year: number;
    quarter: number;
    month?: number | null;
    teams?: string[];
    force_refresh?: boolean;
  }) => api.post<WorkTypeReportResponse>('/work-type-report', body),

  /**
   * POST /work-type-report/build/stream — SSE-streamed build.
   * Calls onEvent for each SSE frame. Resolves on `done`, rejects on `error`.
   */
  buildStream: async (
    body: {
      work_type_id: string;
      year: number;
      quarter: number;
      month?: number | null;
      teams?: string[];
      force_refresh?: boolean;
    },
    onEvent: (e: BuildEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> => {
    const url = `${BASE_URL}/work-type-report/build/stream`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
      credentials: 'include',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const event = JSON.parse(line.slice(6)) as BuildEvent;
        onEvent(event);
        if (event.type === 'error') throw new Error(event.detail);
        if (event.type === 'done' || event.type === 'cancelled') return;
      }
    }
  },

  // ---- Candidate actions ----

  acceptCandidate: (body: CandidateAcceptRequest) =>
    api.post<{ ok: true; theme_id: string }>('/work-type-report/candidates/accept', body),

  mergeCandidate: (body: CandidateMergeRequest) =>
    api.post<{ ok: true }>('/work-type-report/candidates/merge', body),

  ignoreCandidate: (body: CandidateIgnoreRequest) =>
    api.post<{ ok: true }>('/work-type-report/candidates/ignore', body),

  manualClassify: (body: ManualClassifyRequest) =>
    api.post<{ ok: true }>('/work-type-report/manual-classify', body),

  // ---- Layouts ----

  listLayouts: (workTypeId: string, signal?: AbortSignal) =>
    api.get<LayoutOut[]>('/work-type-report/layouts', { work_type_id: workTypeId }, signal),

  createLayout: (body: LayoutCreateRequest) =>
    api.post<LayoutOut>('/work-type-report/layouts', body),

  deleteLayout: (layoutId: string) =>
    api.del<{ ok: true }>(`/work-type-report/layouts/${encodeURIComponent(layoutId)}`),

  /** Download xlsx binary — used by toolbar (Task 12). Returns void; triggers browser download. */
  downloadXlsx: (snapshotId: string) =>
    api.download(`/work-type-report/export/${encodeURIComponent(snapshotId)}.xlsx`),

  // ---- Theme aliases (embedding training) ----

  addAlias: (themeId: string, alias: string) =>
    api.post<{ theme_id: string; aliases: string[] }>(
      `/work-type-report/themes/${encodeURIComponent(themeId)}/aliases`,
      { alias },
    ),

  removeAlias: (themeId: string, alias: string) =>
    api.del<{ theme_id: string; aliases: string[] }>(
      `/work-type-report/themes/${encodeURIComponent(themeId)}/aliases?alias=${encodeURIComponent(alias)}`,
    ),

  // ---- Embedding threshold ----

  getEmbeddingThreshold: () =>
    api.get<{ threshold: number }>('/work-type-report/settings/embedding-threshold'),

  setEmbeddingThreshold: (threshold: number) =>
    api.put<{ threshold: number }>(
      '/work-type-report/settings/embedding-threshold',
      { threshold },
    ),
};
