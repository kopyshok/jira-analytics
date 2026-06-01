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

export const batchSetCategory = (issueIds: string[], categoryCode: string | null) =>
  api.put<BatchCategoryResponse>('/issues/batch-category', {
    issue_ids: issueIds,
    category_code: categoryCode,
  });

export interface VerifyIssueResponse {
  ok: boolean;
  verified_count: number;
}

export const verifyIssue = (
  issueId: string,
  cascade: boolean,
  requireChildVerification: boolean,
) =>
  api.post<VerifyIssueResponse>(`/issues/${issueId}/verify`, {
    cascade,
    require_child_verification: requireChildVerification,
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

export const getIssueChildrenByTab = (parentId: string, tab: string, limit = 200) =>
  api.get<IssueTreeRootNode[]>(`/issues/${parentId}/children`, { tab, limit: String(limit) });

export const getEpicCandidates = (
  params: { project_keys?: string; teams?: string },
  signal?: AbortSignal,
) => api.get<EpicCandidateApi[]>('/issues/tree/epic-candidates', params as Record<string, string | undefined>, signal);
