import { api } from './client';

export type AIStatus = { enabled: boolean };

export const aiStatusApi = {
  get: () => api.get<AIStatus>('/ai-status'),
  set: (enabled: boolean) =>
    api.put('/settings/generic', { key: 'ai_enabled', value: enabled ? 'true' : 'false' }),
};
