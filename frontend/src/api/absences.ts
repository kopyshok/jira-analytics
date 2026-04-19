import { api } from './client';
import type { AbsenceResponse, AbsenceCreateRequest } from '../types/api';

export const getAbsences = (employeeId?: string) =>
  api.get<AbsenceResponse[]>('/capacity/absences', { employee_id: employeeId });

export const addAbsence = (data: AbsenceCreateRequest) =>
  api.post<AbsenceResponse>('/capacity/absences', data);

export const removeAbsence = (id: string) =>
  api.del(`/capacity/absences/${id}`);
