// @vitest-environment jsdom
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ScenarioResponse } from '../types/api';
import { useDeleteScenario } from './usePlanning';

const deleteScenario = vi.fn();
vi.mock('../api/planning', async (orig) => ({
  ...(await orig<typeof import('../api/planning')>()),
  deleteScenario: (id: string) => deleteScenario(id),
}));

const LIST_KEY = ['planning', 'scenarios', undefined, undefined, undefined, undefined];
const sc = (id: string) => ({ id, name: id }) as ScenarioResponse;

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  qc.setQueryData(LIST_KEY, [sc('A'), sc('B')]);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useDeleteScenario(), { wrapper });
  return { qc, result };
}

describe('useDeleteScenario', () => {
  it('сервер не удалил — сценарий возвращается в список', async () => {
    deleteScenario.mockRejectedValueOnce(new Error('нет связи'));
    const { qc, result } = setup();
    await act(async () => {
      await result.current.mutateAsync('A').catch(() => {});
    });
    expect(qc.getQueryData<ScenarioResponse[]>(LIST_KEY)?.map(s => s.id)).toEqual(['A', 'B']);
  });

  it('сервер удалил — сценария в списке нет', async () => {
    deleteScenario.mockResolvedValueOnce(undefined);
    const { qc, result } = setup();
    await act(async () => {
      await result.current.mutateAsync('A');
    });
    expect(qc.getQueryData<ScenarioResponse[]>(LIST_KEY)?.map(s => s.id)).toEqual(['B']);
  });
});
