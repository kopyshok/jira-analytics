import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { PlanDiff } from '../api/resourcePlanning';
import ScenarioComparatorPage from './ScenarioComparatorPage';

const metrics = {
  assignments_count: 3, critical_path_count: 1, last_end_date: '2026-12-25',
  conflicts_open: 0, conflicts_critical: 0,
};
const state = vi.hoisted(() => ({ diff: null as PlanDiff | null, params: '' }));

vi.mock('react-router', () => ({
  useSearchParams: () => [new URLSearchParams(state.params), () => {}],
}));
vi.mock('../hooks/useResourcePlanning', () => ({
  useResourcePlans: () => ({ data: [] }),
  usePlanDiff: () => ({ data: state.diff }),
}));
vi.mock('../hooks/useGlobalTeamFilter', () => ({ useGlobalTeamFilter: () => ({ selectedTeams: [] }) }));
vi.mock('../contexts/HelpContext', () => ({ useRegisterHelp: () => {} }));
vi.mock('../components/shared/PageHeader', () => ({ default: () => null }));

describe('сравнение сценариев — подписи по-русски', () => {
  it('пустые поля выбора планов подписаны по-русски', () => {
    state.diff = null;
    const html = renderToStaticMarkup(<ScenarioComparatorPage />);
    expect(html).toContain('Выберите базовый план');
    expect(html).toContain('Выберите сценарий');
    expect(html).not.toMatch(/baseline|scenario/);
  });

  it('типы изменений, фазы и дата окончания — без английских кодов', () => {
    state.params = 'base=b&scen=s';
    state.diff = {
      baseline_id: 'b', scenario_id: 's',
      baseline_metrics: metrics, scenario_metrics: metrics,
      assignment_shifts: [
        { backlog_item_id: '1', backlog_item_title: 'A', phase: 'dev', part_number: 1, kind: 'added' },
        { backlog_item_id: '2', backlog_item_title: 'B', phase: 'qa', part_number: 1, kind: 'removed' },
        { backlog_item_id: '3', backlog_item_title: 'C', phase: 'analyst', part_number: 1, kind: 'shifted', start_delta_days: 2 },
      ],
    };
    const html = renderToStaticMarkup(<ScenarioComparatorPage />);
    for (const text of ['Добавлено', 'Убрано', 'Сдвинуто', 'Разработка', 'Последняя дата окончания', '25.12.2026']) {
      expect(html).toContain(text);
    }
    expect(html).not.toMatch(/>(added|removed|shifted|dev|qa|analyst)</);
    expect(html).not.toContain('end date');
  });
});
