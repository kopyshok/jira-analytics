import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getScenarios, deleteScenario, generateScenario, capacityPreview } from '../api/planning';
import type { CapacityPreviewRequest } from '../types/planning';

export const useScenarios = (year?: string, quarter?: string) =>
  useQuery({
    queryKey: ['planning', 'scenarios', year, quarter],
    queryFn: () => getScenarios(year, quarter),
  });

export const useGenerateScenario = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: generateScenario,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['planning'] }),
  });
};

export const useDeleteScenario = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteScenario,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['planning'] }),
  });
};

/** Live-расчёт ёмкости для страницы «Сценарии». Сервер принимает список
 *  backlog_item_ids и возвращает суммарный capacity/demand + разрез по ролям
 *  и сотрудникам. Запрос отключается, пока year/quarter не заданы. */
export const useCapacityPreview = (req: CapacityPreviewRequest) =>
  useQuery({
    queryKey: ['planning', 'capacity-preview', req],
    queryFn: () => capacityPreview(req),
    staleTime: 10_000,
    enabled: !!req.year && !!req.quarter,
  });
