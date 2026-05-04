import { api } from './client';

export type GeminiModelInfo = { id: string; label: string; version: number };
export type OpenRouterModelInfo = { id: string; label: string; context_length: number };
export type PromptDefault = { system_role: string; format_spec: string };

export const llmApi = {
  test: () => api.post<{ ok: boolean; provider: string; model: string; error?: string | null }>('/llm/test'),
  regenerateAll: () => api.post<{ started: boolean }>('/llm/regenerate-all'),
  listGeminiModels: () => api.get<GeminiModelInfo[]>('/llm/gemini/models'),
  listOpenRouterModels: () => api.get<OpenRouterModelInfo[]>('/llm/openrouter/models'),
  getPromptDefault: () => api.get<PromptDefault>('/llm/prompt-default'),
};
