// @vitest-environment jsdom
import { act, cleanup, fireEvent, render } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AbsenceResponse } from '../../types/api';
import AbsenceHeatmap from './AbsenceHeatmap';

// Считаем, сколько подсказок строит карта: раньше — по одной на каждую клетку,
// на 700 сотрудниках это 64 тысячи и десяток секунд отрисовки.
const tooltipRenders = vi.hoisted(() => ({ count: 0 }));
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();
  return {
    ...actual,
    Tooltip: ({ title, open, children }: { title?: ReactNode; open?: boolean; children?: ReactNode }) => {
      tooltipRenders.count += 1;
      return <span data-testid="tip" data-open={String(open)} data-title={String(title)}>{children}</span>;
    },
  };
});

const employees = Array.from({ length: 30 }, (_, i) => ({ id: `e${i}`, display_name: `Сотрудник ${i}` }));
const absences: AbsenceResponse[] = [{
  id: 'a1', employee_id: 'e1', start_date: '2026-10-05', end_date: '2026-10-09',
  reason_id: 'r', reason_code: 'vac', reason_label: 'Отпуск', reason_is_planned: true,
  reason_color: '#ff0000', hours_total: null,
}];

describe('карта отсутствий', () => {
  beforeEach(() => { tooltipRenders.count = 0; vi.useFakeTimers(); });
  afterEach(() => { cleanup(); vi.useRealTimers(); });

  it('строит клетку на каждый день, но не подсказку на каждую клетку', () => {
    const { container } = render(<AbsenceHeatmap year={2026} quarter={4} employees={employees} absences={absences} />);
    expect(tooltipRenders.count).toBe(0);
    expect(container.querySelectorAll('[data-day]')).toHaveLength(30 * 92);
  });

  it('клетка отсутствия закрашена цветом причины', () => {
    const { container } = render(<AbsenceHeatmap year={2026} quarter={4} employees={employees} absences={absences} />);
    const row = container.querySelector('[data-row="1"]')!;
    const cells = row.querySelectorAll<HTMLElement>('[data-day]');
    expect(cells[4].style.background).toBe('rgb(255, 0, 0)');
    expect(cells[3].style.background).toBe('');
  });

  it('при наведении — одна подсказка с текстом клетки', () => {
    const { container, getAllByTestId } = render(
      <AbsenceHeatmap year={2026} quarter={4} employees={employees} absences={absences} />,
    );
    const cell = container.querySelector('[data-row="1"]')!.querySelectorAll('[data-day]')[6];
    fireEvent.mouseOver(cell);
    act(() => { vi.advanceTimersByTime(400); });
    const tips = getAllByTestId('tip');
    expect(tips).toHaveLength(1);
    expect(tips[0].dataset.title).toBe('Сотрудник 1: Отпуск, 05.10–09.10');

    fireEvent.mouseLeave(container.querySelector('[data-day]')!.closest('[data-grid]')!);
    expect(container.querySelectorAll('[data-testid="tip"]')).toHaveLength(0);
  });
});
