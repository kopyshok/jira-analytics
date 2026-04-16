import { useQuery } from '@tanstack/react-query';
import { getHoursByEmployee, getHoursByProject, getHoursByCategory, getHoursByPeriod, getContextSwitching } from '../api/analytics';
import { getEmployees } from '../api/employees';
import { getProjects } from '../api/projects';

export const useHoursByEmployee = (start?: string, end?: string, employeeId?: string, projectKey?: string) =>
  useQuery({ queryKey: ['analytics', 'by-employee', start, end, employeeId, projectKey], queryFn: () => getHoursByEmployee(start, end, employeeId, projectKey) });

export const useHoursByProject = (start?: string, end?: string, employeeId?: string, projectKey?: string) =>
  useQuery({ queryKey: ['analytics', 'by-project', start, end, employeeId, projectKey], queryFn: () => getHoursByProject(start, end, employeeId, projectKey) });

export const useHoursByCategory = (start?: string, end?: string, employeeId?: string, projectKey?: string) =>
  useQuery({ queryKey: ['analytics', 'by-category', start, end, employeeId, projectKey], queryFn: () => getHoursByCategory(start, end, employeeId, projectKey) });

export const useHoursByPeriod = (period: string, start?: string, end?: string, employeeId?: string, projectKey?: string) =>
  useQuery({ queryKey: ['analytics', 'by-period', period, start, end, employeeId, projectKey], queryFn: () => getHoursByPeriod(period, start, end, employeeId, projectKey) });

export const useContextSwitching = (start?: string, end?: string, employeeId?: string, projectKey?: string) =>
  useQuery({ queryKey: ['analytics', 'context-switching', start, end, employeeId, projectKey], queryFn: () => getContextSwitching(start, end, employeeId, projectKey) });

export const useEmployeesForFilter = () =>
  useQuery({ queryKey: ['employees'], queryFn: () => getEmployees() });

export const useProjectsForFilter = () =>
  useQuery({ queryKey: ['projects'], queryFn: () => getProjects() });
