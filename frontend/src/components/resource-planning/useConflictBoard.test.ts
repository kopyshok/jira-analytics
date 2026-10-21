import { describe, it, expect } from 'vitest';
import type { ConflictOut } from '../../api/resourcePlanning';
import { groupConflicts, isLiveConflict, splitConflicts } from './useConflictBoard';

const c = (over: Partial<ConflictOut>): ConflictOut => ({
  id: 'c1',
  type: 'OVERLOAD_HIGH',
  severity: 'critical',
  status: 'open',
  backlog_item_id: 'i1',
  backlog_item_title: 'Миграция',
  employee_id: 'e1',
  employee_name: 'Ковалёв',
  assignment_id: 'a1',
  window_start: null,
  window_end: null,
  metric_value: null,
  message: 'перегрузка',
  created_at: '',
  updated_at: '',
  ...over,
});

describe('splitConflicts', () => {
  const list = [
    c({ id: '1' }),
    c({ id: '2', status: 'muted' }),
    c({ id: '3', status: 'resolved' }),
    c({ id: '4', severity: 'info' }),
    c({ id: '5', status: 'acknowledged', severity: 'warning' }),
  ];

  it('информационные не показываются, погашенные отдельно', () => {
    const { active, hidden, visible } = splitConflicts(list, false);
    expect(active.map((x) => x.id)).toEqual(['1', '5']);
    expect(hidden.map((x) => x.id)).toEqual(['2', '3']);
    expect(visible.map((x) => x.id)).toEqual(['1', '5']);
  });

  it('«показать погашенные» добавляет их в конец', () => {
    expect(splitConflicts(list, true).visible.map((x) => x.id)).toEqual(['1', '5', '2', '3']);
  });
});

describe('groupConflicts', () => {
  const list = [
    c({ id: '1', backlog_item_id: 'b', backlog_item_title: 'Биллинг', type: 'LATE_START' }),
    c({ id: '2', backlog_item_id: 'a', backlog_item_title: 'Анализ', employee_id: null, type: 'UNKNOWN_NEW' }),
    c({ id: '3', backlog_item_id: 'b', backlog_item_title: 'Биллинг' }),
  ];

  it('по задачам — группы по алфавиту', () => {
    const groups = groupConflicts(list, 'item');
    expect(groups.map((g) => g.label)).toEqual(['Анализ', 'Биллинг']);
    expect(groups[1].items.map((x) => x.id)).toEqual(['1', '3']);
  });

  it('по сотрудникам — без сотрудника отдельной группой', () => {
    const labels = groupConflicts(list, 'employee').map((g) => g.label);
    expect(labels).toContain('Без сотрудника');
    expect(labels).toContain('Ковалёв');
  });

  it('по типу — незнакомый тип уходит в «Прочее»', () => {
    const labels = groupConflicts(list, 'type').map((g) => g.label);
    expect(labels).toEqual(['Поздний старт', 'Прочее', 'Сильная перегрузка']);
  });
});

describe('isLiveConflict', () => {
  it('живой — по признаку или по префиксу id', () => {
    expect(isLiveConflict(c({ is_live: true }))).toBe(true);
    expect(isLiveConflict(c({ id: 'live:x' }))).toBe(true);
    expect(isLiveConflict(c({}))).toBe(false);
  });
});
