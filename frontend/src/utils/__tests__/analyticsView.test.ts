import { describe, expect, it } from 'vitest';
import {
  analyticsExportParams, formatHours, formatInt, formatIsoDate, formatPct, formatPct1,
  isProjectCategory, periodBounds, planTone,
} from '../analyticsView';

// Intl ставит неразрывный пробел между разрядами — сравниваем по обычному.
const plain = (s: string) => s.replace(/\s/g, ' ');

describe('periodBounds', () => {
  it('квартал — с первого дня первого месяца по последний день третьего', () => {
    expect(periodBounds(2026, 4)).toEqual({ start: '2026-10-01', end: '2026-12-31' });
    expect(periodBounds(2026, 1)).toEqual({ start: '2026-01-01', end: '2026-03-31' });
  });
  it('месяц внутри квартала — его границы, февраль високосного года', () => {
    expect(periodBounds(2026, 4, 11)).toEqual({ start: '2026-11-01', end: '2026-11-30' });
    expect(periodBounds(2028, 1, 2)).toEqual({ start: '2028-02-01', end: '2028-02-29' });
  });
});

describe('analyticsExportParams', () => {
  const base = {
    period: { year: 2026, quarter: 4 },
    selectedTeam: 'all',
    selectedTeams: [],
    selectedSubgroups: [],
    visibleColumns: [],
    hierarchy: false,
  };
  it('без фильтров — только год и квартал', () => {
    expect(analyticsExportParams(base).toString()).toBe('year=2026&quarter=4');
  });
  it('команда со страницы главнее командного фильтра шапки', () => {
    const p = analyticsExportParams({ ...base, selectedTeam: 'ERP', selectedTeams: ['ERP', 'Склад'] });
    expect(p.get('teams')).toBe('ERP');
    const all = analyticsExportParams({ ...base, selectedTeams: ['ERP', 'Склад'] });
    expect(all.get('teams')).toBe('ERP,Склад');
  });
  it('переносит все отборы, колонки и иерархию', () => {
    const p = analyticsExportParams({
      ...base,
      period: { year: 2026, quarter: 4, month: 10 },
      startDate: '2026-10-01',
      endDate: '2026-10-16',
      selectedSubgroups: ['g1'],
      employeeId: 'e1',
      taskQ: 'ERP-1',
      workType: 'dev',
      category: 'quarterly_tasks',
      visibleColumns: ['plan_hours', 'pct_plan'],
      hierarchy: true,
    });
    expect(Object.fromEntries(p)).toEqual({
      year: '2026', quarter: '4', month: '10',
      start_date: '2026-10-01', end_date: '2026-10-16',
      subgroups: 'g1', employee_id: 'e1', task_query: 'ERP-1',
      work_type_codes: 'dev', category_codes: 'quarterly_tasks',
      columns: 'plan_hours,pct_plan', hierarchy: 'true',
    });
  });
});

describe('planTone', () => {
  it.each([
    [null, null],
    [undefined, null],
    [158, 'over'],
    [110.1, 'over'],
    [110, 'ok'],
    [95, 'ok'],
    [70, 'ok'],
    [69.9, 'under'],
    [0, 'under'],
  ])('%s → %s', (pct, tone) => {
    expect(planTone(pct as number | null | undefined)).toBe(tone);
  });
});

describe('форматы чисел', () => {
  it('часы с одним знаком и разрядами', () => {
    expect(plain(formatHours(3412.5))).toBe('3 412,5');
    expect(plain(formatHours(9))).toBe('9,0');
  });
  it('целые с разрядами', () => {
    expect(plain(formatInt(1320))).toBe('1 320');
    expect(formatInt(91.6)).toBe('92');
  });
  it('проценты: целый и с одним знаком', () => {
    expect(formatPct(94.4)).toBe('94%');
    expect(formatPct1(56.7)).toBe('56,7%');
  });
  it('дата ISO → дд.мм.гггг', () => {
    expect(formatIsoDate('2026-10-14T09:30:00+03:00')).toBe('14.10.2026');
    expect(formatIsoDate('2026-10-15')).toBe('15.10.2026');
    expect(formatIsoDate(null)).toBe('—');
    expect(formatIsoDate('вчера')).toBe('—');
  });
});

describe('isProjectCategory', () => {
  it('страница проекта есть у квартальных и архивных целевых задач', () => {
    expect(isProjectCategory('quarterly_tasks')).toBe(true);
    expect(isProjectCategory('archive_target')).toBe(true);
    expect(isProjectCategory('support')).toBe(false);
    expect(isProjectCategory(null)).toBe(false);
  });
});
