import { api } from './client';
import type { IssueTreeNode } from '../types/api';

export const getIssueTree = (
  params?: { project_keys?: string; teams?: string },
  signal?: AbortSignal,
) => api.get<IssueTreeNode[]>('/issues/tree', params as Record<string, string | undefined>, signal);

export const setIssueCategory = (issueId: string, categoryCode: string | null) =>
  api.put<{ ok: boolean }>(`/issues/${issueId}/category`, { category_code: categoryCode });

export const setIssueInclude = (issueId: string, include: boolean, recursive: boolean = false) =>
  api.put<{ ok: boolean }>(`/issues/${issueId}/include`, { include, recursive });

export const batchSetCategory = (issueIds: string[], categoryCode: string | null) =>
  api.put<{ ok: boolean; updated: number }>('/issues/batch-category', {
    issue_ids: issueIds,
    category_code: categoryCode,
  });
