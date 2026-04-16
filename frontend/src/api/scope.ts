import { api } from './client';
import type { ScopeProjectResponse, ScopeRootResponse, CategoryOverrideResponse } from '../types/api';

// Scope Projects
export const getScopeProjects = () => api.get<ScopeProjectResponse[]>('/scope/projects');
export const addScopeProject = (data: { jira_project_key: string }) => api.post<ScopeProjectResponse>('/scope/projects', data);
export const removeScopeProject = (key: string) => api.del(`/scope/projects/${key}`);

// Scope Roots
export const getScopeRoots = () => api.get<ScopeRootResponse[]>('/scope/roots');
export const addScopeRoot = (data: { category_code: string; jira_issue_key: string }) => api.post<ScopeRootResponse>('/scope/roots', data);
export const removeScopeRoot = (id: string) => api.del(`/scope/roots/${id}`);

// Category Overrides
export const getOverrides = () => api.get<CategoryOverrideResponse[]>('/scope/overrides');
export const addOverride = (data: { jira_issue_key: string; category_code: string }) => api.post<CategoryOverrideResponse>('/scope/overrides', data);
export const removeOverride = (key: string) => api.del(`/scope/overrides/${key}`);
