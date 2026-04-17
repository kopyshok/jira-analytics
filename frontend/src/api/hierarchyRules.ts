import { api } from './client';
import type { HierarchyRule, HierarchyRuleCreate, HierarchyRuleUpdate } from '../types/api';

export const listHierarchyRules = () =>
  api.get<HierarchyRule[]>('/hierarchy-rules');

export const createHierarchyRule = (body: HierarchyRuleCreate) =>
  api.post<HierarchyRule>('/hierarchy-rules', body);

export const updateHierarchyRule = (id: string, body: HierarchyRuleUpdate) =>
  api.patch<HierarchyRule>(`/hierarchy-rules/${id}`, body);

export const deleteHierarchyRule = (id: string) =>
  api.del<{ status: string }>(`/hierarchy-rules/${id}`);

export const reorderHierarchyRules = (ids: string[]) =>
  api.post<HierarchyRule[]>('/hierarchy-rules/reorder', { ids });
