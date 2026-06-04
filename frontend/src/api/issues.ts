import { api } from './client';
import type {
  IssueChildNode,
  IssueContextResponse,
  IssueTreeNode,
  IssueTreeRootNode,
  IssueTreeCounts,
  EpicCandidateApi,
  BulkFilter,
  BulkPreviewResponse,
  BulkApplyResponse,
  BulkAcceptResponse,
  BulkCascadeResponse,
} from '../types/api';

export const getIssueTree = (
  params?: { project_keys?: string; teams?: string },
  signal?: AbortSignal,
) => api.get<IssueTreeNode[]>('/issues/tree', params as Record<string, string | undefined>, signal);

export interface SetCategoryResponse {
  ok: boolean;
  key: string;
  assigned_category: string | null;
  include_in_analysis: boolean;
  auto_excluded: boolean;
}

export const setIssueCategory = (issueId: string, categoryCode: string | null) =>
  api.put<SetCategoryResponse>(`/issues/${issueId}/category`, { category_code: categoryCode });

export const setIssueInclude = (issueId: string, include: boolean, recursive: boolean = false) =>
  api.put<{ ok: boolean }>(`/issues/${issueId}/include`, { include, recursive });

export interface BatchCategoryResponse {
  ok: boolean;
  updated: number;
  archived_ids: string[];
  skipped_containers: string[];
}

export const batchSetCategory = (
  issueIds: string[],
  categoryCode: string | null,
  verify: boolean = false,
) =>
  api.put<BatchCategoryResponse>('/issues/batch-category', {
    issue_ids: issueIds,
    category_code: categoryCode,
    verify,
  });

export interface VerifyIssueResponse {
  ok: boolean;
  verified_count: number;
}

export const verifyIssue = (
  issueId: string,
  cascade: boolean,
  requireChildVerification: boolean,
  categoryCode?: string | null,
  hasCategoryCode: boolean = false,
) =>
  api.post<VerifyIssueResponse>(`/issues/${issueId}/verify`, {
    cascade,
    require_child_verification: requireChildVerification,
    category_code: categoryCode ?? null,
    has_category_code: hasCategoryCode,
  });

export const getIssueContext = (issueId: string) =>
  api.get<IssueContextResponse>(`/issues/${issueId}/context`);

export const getIssueChildren = (parentId: string, limit = 200) =>
  api.get<IssueChildNode[]>(`/issues/${parentId}/children`, { limit: String(limit) });

export const bulkPreview = (filters: BulkFilter, limit = 200) =>
  api.post<BulkPreviewResponse>('/issues/bulk/preview', { filters, limit });

export const bulkArchive = (filters: BulkFilter, categoryCode: 'archive' | 'archive_target') =>
  api.post<BulkApplyResponse>('/issues/bulk/archive', { filters, category_code: categoryCode });

export const bulkAcceptSuggestions = (filters: BulkFilter) =>
  api.post<BulkAcceptResponse>('/issues/bulk/accept-suggestions', { filters });

export const bulkCascadeInherit = (ancestorIds: string[]) =>
  api.post<BulkCascadeResponse>('/issues/bulk/cascade-inherit', { ancestor_ids: ancestorIds });

export const getTreeRoots = (
  params: { project_keys?: string; teams?: string; tab: string; search?: string },
  signal?: AbortSignal,
) => api.get<IssueTreeRootNode[]>('/issues/tree/roots', params as Record<string, string | undefined>, signal);

export const getTreeCounts = (
  params: { project_keys?: string; teams?: string },
  signal?: AbortSignal,
) => api.get<IssueTreeCounts>('/issues/tree/counts', params as Record<string, string | undefined>, signal);

export const getIssueChildrenByTab = (
  parentId: string,
  tab: string,
  opts: { teams?: string; project_keys?: string; search?: string; limit?: number } = {},
) =>
  api.get<IssueTreeRootNode[]>(`/issues/${parentId}/children`, {
    tab,
    limit: String(opts.limit ?? 200),
    teams: opts.teams,
    project_keys: opts.project_keys,
    search: opts.search,
  });

export const getEpicCandidates = (
  params: { project_keys?: string; teams?: string },
  signal?: AbortSignal,
) => api.get<EpicCandidateApi[]>('/issues/tree/epic-candidates', params as Record<string, string | undefined>, signal);

export interface HoursBreakdownData {
  issue_id: string;
  year: number;
  quarter: number;
  plan: Record<string, number>;
  fact_past: Record<string, number>;
  fact_current: Record<string, number>;
  approved: Record<string, number>;
  planable: Record<string, number>;
  draft: Record<string, number>;
  flags: { overrun: boolean; plan_missing: boolean; draft_exceeds_planable: boolean };
}

export const getHoursBreakdown = (issueId: string, year: number, quarter: number) =>
  api.get<HoursBreakdownData>(`/issues/${issueId}/hours-breakdown`, {
    year: String(year),
    quarter: String(quarter),
  });

export interface PlanAuditRow {
  id: string;
  role: string;
  value_before: number | null;
  value_after: number | null;
  source: string;
  user_id: string | null;
  comment: string | null;
  created_at: string;
}

export interface PlanConflict {
  role: string;
  audit_id: string;
  value_jira: number | null;
  value_before: number | null;
}

export const patchPlan = (
  issueId: string,
  roleHours: Record<string, number | null>,
  comment: string,
): Promise<{ plan: Record<string, number | null> }> =>
  api.patch(`/issues/${issueId}/plan`, { role_hours: roleHours, comment });

export const revertPlan = (
  issueId: string,
  auditId?: string,
): Promise<{ plan: Record<string, number | null> }> =>
  api.post(`/issues/${issueId}/plan/revert`, { audit_id: auditId ?? null });

export const getPlanHistory = (issueId: string): Promise<PlanAuditRow[]> =>
  api.get<PlanAuditRow[]>(`/issues/${issueId}/plan-history`);

export const resolvePlanConflict = (
  issueId: string,
  action: 'accept_jira' | 'ignore',
  role: string,
): Promise<{ ok: boolean }> =>
  api.post(`/issues/${issueId}/plan/conflict-resolve`, { action, role });

export const getPlanConflicts = (issueId: string): Promise<PlanConflict[]> =>
  api.get<PlanConflict[]>(`/issues/${issueId}/plan-conflicts`);
