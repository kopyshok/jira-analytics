import { api } from './client';
import type {
  ProductionCalendarDayResponse,
  ProductionCalendarUpsertRequest,
  ProductionCalendarSyncResponse,
} from '../types/api';

export const listProductionCalendarYear = (year: number) =>
  api.get<ProductionCalendarDayResponse[]>('/production-calendar', {
    year: String(year),
  });

export const upsertProductionCalendarDay = (req: ProductionCalendarUpsertRequest) =>
  api.put<ProductionCalendarDayResponse>('/production-calendar', req);

export const deleteProductionCalendarDay = (date: string) =>
  api.del<{ ok: boolean }>(`/production-calendar/${date}`);

export const syncProductionCalendarYear = (year: number) =>
  api.post<ProductionCalendarSyncResponse>(
    `/production-calendar/sync?year=${year}`,
    {},
  );
