import { useQuery } from '@tanstack/react-query';
import { getHoursByEmployee, getHoursByProject, getHoursByCategory, getHoursByPeriod, getContextSwitching } from '../api/analytics';

export const useHoursByEmployee = (start?: string, end?: string) =>
  useQuery({ queryKey: ['analytics', 'by-employee', start, end], queryFn: () => getHoursByEmployee(start, end) });

export const useHoursByProject = (start?: string, end?: string) =>
  useQuery({ queryKey: ['analytics', 'by-project', start, end], queryFn: () => getHoursByProject(start, end) });

export const useHoursByCategory = (start?: string, end?: string) =>
  useQuery({ queryKey: ['analytics', 'by-category', start, end], queryFn: () => getHoursByCategory(start, end) });

export const useHoursByPeriod = (period: string, start?: string, end?: string) =>
  useQuery({ queryKey: ['analytics', 'by-period', period, start, end], queryFn: () => getHoursByPeriod(period, start, end) });

export const useContextSwitching = (start?: string, end?: string) =>
  useQuery({ queryKey: ['analytics', 'context-switching', start, end], queryFn: () => getContextSwitching(start, end) });
