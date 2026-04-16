import { api } from './client';
import type { AggregateRowResponse, ContextSwitchRowResponse } from '../types/api';

const dateParams = (start?: string, end?: string) => ({ start, end });

export const getHoursByEmployee = (start?: string, end?: string) =>
  api.get<AggregateRowResponse[]>('/analytics/hours/by-employee', dateParams(start, end));

export const getHoursByProject = (start?: string, end?: string) =>
  api.get<AggregateRowResponse[]>('/analytics/hours/by-project', dateParams(start, end));

export const getHoursByCategory = (start?: string, end?: string) =>
  api.get<AggregateRowResponse[]>('/analytics/hours/by-category', dateParams(start, end));

export const getHoursByPeriod = (period: string, start?: string, end?: string) =>
  api.get<AggregateRowResponse[]>('/analytics/hours/by-period', { period, ...dateParams(start, end) });

export const getContextSwitching = (start?: string, end?: string) =>
  api.get<ContextSwitchRowResponse[]>('/analytics/context-switching', dateParams(start, end));
