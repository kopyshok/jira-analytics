import { api } from './client';
import type { IssueTreeNode } from '../types/api';

export const getIssueTree = (params?: { project_keys?: string; team?: string }) =>
  api.get<IssueTreeNode[]>('/issues/tree', params as Record<string, string | undefined>);

export const setIssueCategory = (issueId: string, categoryCode: string | null) =>
  api.put<{ ok: boolean }>(`/issues/${issueId}/category`, { category_code: categoryCode });

export const setIssueInclude = (issueId: string, include: boolean, recursive: boolean = false) =>
  api.put<{ ok: boolean }>(`/issues/${issueId}/include`, { include, recursive });
