import { describe, it, expect } from 'vitest';
import { formatNumber, isoDateToRu } from '../format';

describe('formatNumber', () => {
  it('keeps the old dot format by default', () => {
    expect(formatNumber(3412.5, 1)).toBe('3412.5');
    expect(formatNumber(94.4, 0)).toBe('94');
  });

  it('formats in Russian: digit groups and decimal comma', () => {
    expect(formatNumber(3412.5, 1, true).replace(/\s/g, ' ')).toBe('3 412,5');
    expect(formatNumber(1320, 0, true).replace(/\s/g, ' ')).toBe('1 320');
    expect(formatNumber(0, 1, true)).toBe('0,0');
  });
});

describe('isoDateToRu', () => {
  it('reorders the date part without timezone shifts', () => {
    expect(isoDateToRu('2026-10-14')).toBe('14.10.2026');
    expect(isoDateToRu('2026-10-14T23:30:00')).toBe('14.10.2026');
  });
});
