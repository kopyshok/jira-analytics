import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { invalidateForEntity } from './useEventStream';

function invalidatedKeys(entity: string) {
  const qc = new QueryClient();
  const spy = vi.spyOn(qc, 'invalidateQueries').mockResolvedValue(undefined);
  invalidateForEntity(entity, qc);
  return spy.mock.calls.map(([filters]) => filters?.queryKey);
}

describe('invalidateForEntity', () => {
  it('правка ресурсного плана обновляет диаграмму, список планов, кандидатов, качество и сравнение', () => {
    expect(invalidatedKeys('resource_planning')).toEqual([
      ['gantt'],
      ['resource-plans'],
      ['assignment-candidates'],
      ['plan-quality'],
      ['plan-diff'],
    ]);
  });
});

describe('invalidateForEntity — кандидаты', () => {
  it('кандидатов только помечает устаревшими: старый id фазы после пересчёта дал бы 404', () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, 'invalidateQueries').mockResolvedValue(undefined);
    invalidateForEntity('resource_planning', qc);
    const call = spy.mock.calls.find(([f]) => f?.queryKey?.[0] === 'assignment-candidates');
    expect(call?.[0]?.refetchType).toBe('none');
  });
});
