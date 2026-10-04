import { describe, expect, it } from 'vitest';
import {
  formatQuarterParam,
  parseQuarterParam,
  quarterOf,
  quarterOffset,
  shiftQuarter,
} from './deskPeriod';

const cur = { year: 2026, quarter: 4 };

describe('deskPeriod', () => {
  it('определяет квартал даты', () => {
    expect(quarterOf(new Date(2026, 9, 4))).toEqual({ year: 2026, quarter: 4 });
    expect(quarterOf(new Date(2026, 0, 1))).toEqual({ year: 2026, quarter: 1 });
  });

  it('сдвигает через границу года', () => {
    expect(shiftQuarter(cur, 1)).toEqual({ year: 2027, quarter: 1 });
    expect(shiftQuarter({ year: 2026, quarter: 1 }, -1)).toEqual({ year: 2025, quarter: 4 });
    expect(shiftQuarter(cur, -4)).toEqual({ year: 2025, quarter: 4 });
  });

  it('считает отступ от текущего', () => {
    expect(quarterOffset({ year: 2027, quarter: 4 }, cur)).toBe(4);
  });

  it('разбирает параметр адреса', () => {
    expect(parseQuarterParam('2026-3', cur)).toEqual({ year: 2026, quarter: 3 });
    expect(formatQuarterParam({ year: 2026, quarter: 3 })).toBe('2026-3');
  });

  it('отбрасывает мусор и выход за пределы ±4', () => {
    expect(parseQuarterParam(null, cur)).toBeNull();
    expect(parseQuarterParam('abc', cur)).toBeNull();
    expect(parseQuarterParam('2026-5', cur)).toBeNull();
    expect(parseQuarterParam('2025-4', cur)).toEqual({ year: 2025, quarter: 4 });
    expect(parseQuarterParam('2025-3', cur)).toBeNull();
    expect(parseQuarterParam('2027-4', cur)).toEqual({ year: 2027, quarter: 4 });
    expect(parseQuarterParam('2028-1', cur)).toBeNull();
  });
});
