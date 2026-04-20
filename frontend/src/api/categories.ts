import { api } from './client';
import type { CategoryResponse } from '../types/api';

export const listCategories = () =>
  api.get<CategoryResponse[]>('/categories');

export const createCategory = (body: { code: string; label: string; color?: string; sort_order?: number }) =>
  api.post<CategoryResponse>('/categories', body);

export const updateCategory = (
  id: string,
  body: { label?: string; color?: string | null; sort_order?: number; work_type_id?: string | null },
) =>
  api.put<CategoryResponse>(`/categories/${id}`, body);

export const deleteCategory = (id: string) =>
  api.del<{ ok: boolean }>(`/categories/${id}`);
