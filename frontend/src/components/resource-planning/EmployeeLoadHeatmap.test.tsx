import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { EmployeeLoadOut } from '../../api/resourcePlanning';
import EmployeeLoadHeatmap from './EmployeeLoadHeatmap';

vi.mock('../../hooks/useRoles', () => ({
  useRoles: () => ({
    data: [
      { id: 'r1', code: 'dev', label: 'Разработчик', color: '#000', is_active: true, counts_in_planning: true, sort_order: 1 },
      { id: 'r2', code: 'analyst', label: 'Аналитик', color: '#000', is_active: true, counts_in_planning: true, sort_order: 2 },
    ],
  }),
}));

const row = (id: string, role: string): EmployeeLoadOut => ({
  employee_id: id,
  employee_name: `Сотрудник ${id}`,
  employee_role: role,
  days: [{ date: '2026-11-02', pct: 50 }, { date: '2026-11-03', pct: 0 }],
});

describe('загрузка по дням: роль у имени', () => {
  it('показывает название роли из справочника, а не код', () => {
    const html = renderToStaticMarkup(
      <EmployeeLoadHeatmap rows={[row('a', 'dev'), row('b', 'analyst')]} />,
    );
    expect(html).toContain('Разработчик');
    expect(html).toContain('Аналитик');
    expect(html).not.toMatch(/>dev</);
    expect(html).not.toMatch(/>analyst</);
  });
});
