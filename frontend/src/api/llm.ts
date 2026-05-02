import { api } from './client';

export const llmApi = {
  test: () => api.post<{ ok: boolean; provider: string; model: string }>('/llm/test'),
  regenerateAll: () => api.post<{ started: boolean }>('/llm/regenerate-all'),
};
