import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { InvolvementFactResponse } from '../types/api';
import type { QuarterRef } from '../utils/involvementFact';

/**
 * Фактическая вовлечённость команд за квартал. Без квартала сервер берёт
 * последний завершённый — так справочник подписывает «факт». Ключ под
 * «analytics»: правка задач, категорий и сотрудников освежает и его.
 */
export function useInvolvementFact(teams: string[], period?: QuarterRef | null, enabled = true) {
  return useQuery({
    queryKey: ['analytics', 'involvement-fact', teams, period?.year ?? null, period?.quarter ?? null],
    queryFn: ({ signal }) =>
      api.get<InvolvementFactResponse>(
        '/planning/involvement-defaults/fact',
        {
          teams: teams.join(','),
          year: period ? String(period.year) : undefined,
          quarter: period ? String(period.quarter) : undefined,
        },
        signal,
      ),
    enabled: enabled && teams.length > 0,
  });
}
