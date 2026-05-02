import { api } from './client';
import type { ProjectResponse } from '../types/api';

export const getProjects = () => api.get<ProjectResponse[]>('/projects/all');
