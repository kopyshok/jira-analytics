import { describe, expect, it } from 'vitest';
import { currentQuarter, sliceOptions, sumStatusCounts } from './useTeamDeskPage';

describe('currentQuarter', () => {
  it('границы квартала по дате', () => {
    expect(currentQuarter(new Date(2026, 9, 16))).toEqual({ start: '2026-10-01', end: '2026-12-31' });
    expect(currentQuarter(new Date(2026, 1, 3))).toEqual({ start: '2026-01-01', end: '2026-03-31' });
  });
});

describe('sliceOptions', () => {
  it('без пустых и повторов, по алфавиту', () => {
    expect(sliceOptions(['Спринт 2', null, 'Спринт 1', '', 'Спринт 2', undefined])).toEqual(['Спринт 1', 'Спринт 2']);
  });
});

describe('sumStatusCounts', () => {
  it('сумма счётчиков по людям', () => {
    expect(sumStatusCounts([
      { status_counts: { 'В работе': 2, Ревью: 1 } },
      { status_counts: { 'В работе': 3 } },
      {},
    ])).toEqual({ 'В работе': 5, Ревью: 1 });
  });
});
