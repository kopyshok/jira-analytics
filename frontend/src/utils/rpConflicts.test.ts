import { describe, expect, it } from 'vitest';
import type { ConflictOut } from '../api/resourcePlanning';
import { groupConflicts, isLiveConflict, splitConflicts } from './rpConflicts';

const c = (over: Partial<ConflictOut>): ConflictOut => ({
  id: over.id ?? Math.random().toString(36),
  type: 'OVERLOAD_HIGH',
  severity: 'critical',
  status: 'open',
  backlog_item_id: null,
  backlog_item_title: null,
  employee_id: null,
  assignment_id: null,
  window_start: null,
  window_end: null,
  metric_value: null,
  message: '',
  created_at: '',
  updated_at: '',
  ...over,
});

describe('rpConflicts', () => {
  const list = [
    c({ id: 'a', severity: 'critical', backlog_item_id: 'i1', backlog_item_title: 'Яблоко' }),
    c({ id: 'b', severity: 'warning', status: 'muted', backlog_item_id: 'i1', backlog_item_title: 'Яблоко' }),
    c({ id: 'c', severity: 'info' }),
    c({ id: 'd', severity: 'warning', type: 'LATE_START', employee_id: 'e1', employee_name: 'Иванов' }),
  ];

  it('splitConflicts: без информационных; погашенные — только по запросу', () => {
    const shown = splitConflicts(list, false);
    expect(shown.active.map((x) => x.id)).toEqual(['a', 'd']);
    expect(shown.hidden.map((x) => x.id)).toEqual(['b']);
    expect(shown.visible.map((x) => x.id)).toEqual(['a', 'd']);
    expect(splitConflicts(list, true).visible.map((x) => x.id)).toEqual(['a', 'd', 'b']);
  });

  it('groupConflicts: по задаче, сотруднику и типу — по алфавиту подписи', () => {
    const visible = splitConflicts(list, true).visible;
    expect(groupConflicts(visible, 'item').map((g) => [g.label, g.items.length]))
      .toEqual([['Без инициативы', 1], ['Яблоко', 2]]);
    expect(groupConflicts(visible, 'employee').map((g) => g.label)).toEqual(['Без сотрудника', 'Иванов']);
    expect(groupConflicts(visible, 'type').map((g) => g.label)).toEqual(['Поздний старт', 'Сильная перегрузка']);
  });

  it('незнакомый тип — в группу «Прочее»', () => {
    expect(groupConflicts([c({ type: 'NEW_FROM_SERVER' })], 'type')[0].label).toBe('Прочее');
  });

  it('живой конфликт — по признаку или по префиксу id', () => {
    expect(isLiveConflict(c({ is_live: true }))).toBe(true);
    expect(isLiveConflict(c({ id: 'live:123' }))).toBe(true);
    expect(isLiveConflict(c({ id: 'x' }))).toBe(false);
  });
});
