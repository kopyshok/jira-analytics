import { api } from './client';
import type {
  WorkTypeReportResponse,
  CandidateAcceptRequest,
  CandidateMergeRequest,
  CandidateIgnoreRequest,
  ManualClassifyRequest,
  LayoutOut,
  LayoutCreateRequest,
  LayoutUpdateRequest,
} from '../types/workTypeReport';

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

  updateLayout: (layoutId: string, body: LayoutUpdateRequest) =>
    api.patch<LayoutOut>(`/work-type-report/layouts/${encodeURIComponent(layoutId)}`, body),

  deleteLayout: (layoutId: string) =>
    api.del<{ ok: true }>(`/work-type-report/layouts/${encodeURIComponent(layoutId)}`),

  /** Download xlsx binary — used by toolbar (Task 12). Returns void; triggers browser download. */
  downloadXlsx: (snapshotId: string) =>
    api.download(`/work-type-report/export/xlsx/${encodeURIComponent(snapshotId)}`),
};
