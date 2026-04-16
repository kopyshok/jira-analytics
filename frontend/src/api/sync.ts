import { api } from './client';
import type { ConnectionTestResponse, SyncResponse, SyncStatusResponse } from '../types/api';

export const testConnection = () => api.get<ConnectionTestResponse>('/sync/test-connection');
export const syncProjects = () => api.post<SyncResponse>('/sync/projects');
export const syncIssues = () => api.post<SyncResponse>('/sync/issues');
export const syncWorklogs = () => api.post<SyncResponse>('/sync/worklogs');
export const syncComments = () => api.post<SyncResponse>('/sync/comments');
export const syncFull = () => api.post<SyncResponse>('/sync/full');
export const getSyncStatus = () => api.get<SyncStatusResponse[]>('/sync/status');
