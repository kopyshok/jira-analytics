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
