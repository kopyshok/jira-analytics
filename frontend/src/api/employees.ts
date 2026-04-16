import { api } from './client';
import type { EmployeeResponse } from '../types/api';

export const getEmployees = (isActive?: boolean) =>
  api.get<EmployeeResponse[]>('/employees', { is_active: isActive?.toString() });
