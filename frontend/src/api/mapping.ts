import { api } from './client';
import type { MappingResponse } from '../types/api';

export const recalculateAll = () => api.post<MappingResponse>('/mapping/recalculate');
