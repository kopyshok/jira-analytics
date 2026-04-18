import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listProductionCalendarYear,
  upsertProductionCalendarDay,
  deleteProductionCalendarDay,
  syncProductionCalendarYear,
} from '../api/productionCalendar';
import type {
  ProductionCalendarDayResponse,
  ProductionCalendarUpsertRequest,
  ProductionCalendarSyncResponse,
} from '../types/api';

export const useProductionCalendarYear = (year: number) =>
  useQuery({
    queryKey: ['production-calendar', year],
    queryFn: () => listProductionCalendarYear(year),
    staleTime: 60_000,
  });

export const useUpsertProductionCalendarDay = () => {
  const qc = useQueryClient();
  return useMutation<
    ProductionCalendarDayResponse,
    Error,
    ProductionCalendarUpsertRequest
  >({
    mutationFn: upsertProductionCalendarDay,
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ['production-calendar'] }),
  });
};

export const useDeleteProductionCalendarDay = () => {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean }, Error, string>({
    mutationFn: deleteProductionCalendarDay,
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ['production-calendar'] }),
  });
};

export const useSyncProductionCalendarYear = () => {
  const qc = useQueryClient();
  return useMutation<ProductionCalendarSyncResponse, Error, number>({
    mutationFn: syncProductionCalendarYear,
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ['production-calendar'] }),
  });
};
