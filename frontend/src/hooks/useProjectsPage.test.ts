import { describe, expect, it } from 'vitest';
import { currentYearQuarter } from './useProjectsPage';
import { periodBounds } from './useAnalyticsPage';

describe('currentYearQuarter', () => {
  it('год и квартал даты', () => {
    expect(currentYearQuarter(new Date(2026, 9, 17))).toEqual({ year: 2026, quarter: 4 });
    expect(currentYearQuarter(new Date(2027, 0, 1))).toEqual({ year: 2027, quarter: 1 });
  });
});

describe('periodBounds (аналитика)', () => {
  it('квартал и месяц', () => {
    expect(periodBounds(2026, 4)).toEqual({ start: '2026-10-01', end: '2026-12-31' });
    expect(periodBounds(2026, 1, 2)).toEqual({ start: '2026-02-01', end: '2026-02-28' });
  });
});
