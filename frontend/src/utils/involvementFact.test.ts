import { describe, expect, it } from 'vitest';
import type { InvolvementFactCell, InvolvementFactTeam } from '../types/api';
import {
  cellHint, factHint, factTableRows, lastCompletedQuarter, monthLabel, quarterOptions,
} from './involvementFact';

const cell = (over: Partial<InvolvementFactCell> = {}): InvolvementFactCell => ({
  project_hours: 0, logged_hours: 0, norm_hours: 0, fact: null, logged_of_norm: null, ...over,
});

describe('lastCompletedQuarter', () => {
  it('квартал до текущего', () => {
    expect(lastCompletedQuarter(new Date(2026, 9, 4))).toEqual({ year: 2026, quarter: 3 });
    expect(lastCompletedQuarter(new Date(2026, 6, 1))).toEqual({ year: 2026, quarter: 2 });
  });
  it('в первом квартале — четвёртый прошлого года', () => {
    expect(lastCompletedQuarter(new Date(2026, 0, 15))).toEqual({ year: 2025, quarter: 4 });
  });
});

describe('quarterOptions', () => {
  it('текущий квартал помечен, дальше — завершённые по убыванию', () => {
    const opts = quarterOptions(new Date(2026, 9, 4), 3);
    expect(opts.map((o) => o.value)).toEqual(['2026-4', '2026-3', '2026-2']);
    expect(opts[0].label).toBe('Q4 2026 (идёт)');
    expect(opts[1].label).toBe('Q3 2026');
  });
  it('переход через год', () => {
    const opts = quarterOptions(new Date(2026, 1, 1), 3);
    expect(opts.map((o) => o.value)).toEqual(['2026-1', '2025-4', '2025-3']);
  });
});

describe('monthLabel', () => {
  it('название месяца', () => {
    expect(monthLabel(7)).toBe('Июль');
    expect(monthLabel(12)).toBe('Декабрь');
  });
});

describe('factHint', () => {
  it('квартал, число людей и списано от нормы', () => {
    const role = { role: 'dev', people: 3, months: [], total: cell({ fact: 0.43, logged_of_norm: 0.987 }) };
    expect(factHint(role, 2026, 3)).toBe('Q3 2026 · 3 чел. · списано от нормы 99%');
  });
  it('в команде нет людей роли', () => {
    expect(factHint(undefined, 2026, 3)).toBe('Q3 2026 · нет сотрудников с этой ролью');
  });
  it('люди есть, списаний нет', () => {
    const role = { role: 'dev', people: 2, months: [], total: cell({ logged_of_norm: 0 }) };
    expect(factHint(role, 2026, 3)).toBe('За Q3 2026 списаний нет · 2 чел.');
  });
});

describe('cellHint', () => {
  it('часы словами', () => {
    expect(cellHint(cell({ project_hours: 30, logged_hours: 40, norm_hours: 184 })))
      .toBe('На проектных задачах 30 ч из 40 ч списанных · норма 184 ч');
  });
});

describe('factTableRows', () => {
  it('люди роли, затем строка «Среднее по роли»', () => {
    const team: InvolvementFactTeam = {
      team: 'Альфа',
      people: [
        { employee_id: 'a1', name: 'Аня', role: 'analyst', months: [], total: cell() },
        { employee_id: 'd1', name: 'Дима', role: 'dev', months: [], total: cell() },
        { employee_id: 'd2', name: 'Женя', role: 'dev', months: [], total: cell() },
      ],
      roles: [
        { role: 'analyst', people: 1, months: [], total: cell() },
        { role: 'dev', people: 2, months: [], total: cell() },
      ],
    };
    expect(factTableRows(team).map((r) => (r.kind === 'person' ? r.name : `avg:${r.role}`)))
      .toEqual(['Аня', 'avg:analyst', 'Дима', 'Женя', 'avg:dev']);
  });
});
