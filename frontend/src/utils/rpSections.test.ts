import { describe, it, expect } from 'vitest';
import { buildSectionByItem, sortBySection } from './rpSections';
import type { AssignmentOut } from '../api/resourcePlanning';

const a = (over: Partial<AssignmentOut>): AssignmentOut =>
  ({
    id: over.backlog_item_id + ':' + (over.phase ?? 'dev'),
    backlog_item_id: 'i1',
    backlog_item_title: 't',
    phase: 'dev',
    employee_id: null,
    part_number: 1,
    hours_allocated: 8,
    start_date: null,
    end_date: null,
    is_on_critical_path: false,
    slack_days: null,
    is_pinned: false,
    pinned_employee: false,
    pinned_start: false,
    pinned_split: false,
    predecessor_ids: [],
    unavailable_days: [],
    out_of_quarter: false,
    daily_hours: null,
    worklog_hours_actual: 0,
    ...over,
  }) as AssignmentOut;

const names = new Map([['g1', 'Группа 1'], ['g2', 'Группа 2']]);

describe('buildSectionByItem', () => {
  it('берёт группу работы, иначе группу исполнителя из сценария, иначе пусто', () => {
    const map = buildSectionByItem(
      [
        a({ backlog_item_id: 'i1', subgroup_id: 'g1' }),
        a({ backlog_item_id: 'i2', scenario_assignee_employee_id: 'e1' }),
        a({ backlog_item_id: 'i3' }),
      ],
      names,
      { e1: 'Группа 2' },
    );
    expect(map).toEqual({ i1: 'Группа 1', i2: 'Группа 2', i3: '' });
  });
});

describe('sortBySection', () => {
  it('группирует по секциям в порядке реестра, «без группы» — в конец', () => {
    const rows = [
      a({ backlog_item_id: 'i3' }),
      a({ backlog_item_id: 'i2', subgroup_id: 'g2' }),
      a({ backlog_item_id: 'i1', subgroup_id: 'g1' }),
      a({ backlog_item_id: 'i2', subgroup_id: 'g2', phase: 'qa' }),
    ];
    const section = { i1: 'Группа 1', i2: 'Группа 2', i3: '' };
    const out = sortBySection(rows, section, ['Группа 1', 'Группа 2']);
    expect(out.map(r => r.backlog_item_id)).toEqual(['i1', 'i2', 'i2', 'i3']);
  });
});
