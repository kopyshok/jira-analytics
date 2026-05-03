import { api } from './client';

export type GeminiModelInfo = { id: string; label: string; version: number };
export type PromptDefault = { system_role: string; format_spec: string };

export const llmApi = {
  test: () => api.post<{ ok: boolean; provider: string; model: string }>('/llm/test'),
  regenerateAll: () => api.post<{ started: boolean }>('/llm/regenerate-all'),
  listGeminiModels: () => api.get<GeminiModelInfo[]>('/llm/gemini/models'),
  getPromptDefault: () => api.get<PromptDefault>('/llm/prompt-default'),
};
