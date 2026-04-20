import { api } from './client';
import type { CategoryResponse } from '../types/api';

export const listCategories = () =>
  api.get<CategoryResponse[]>('/categories');

export const createCategory = (body: { code: string; label: string; color?: string; sort_order?: number }) =>
  api.post<CategoryResponse>('/categories', body);

export const updateCategory = (id: string, body: Partial<Omit<CategoryResponse, 'id'>>) =>
  api.put<CategoryResponse>(`/categories/${id}`, body);

export const deleteCategory = (id: string) =>
  api.del<{ ok: boolean }>(`/categories/${id}`);
