import { describe, it, expect } from 'vitest';
import { foldOpo, isOpoOff, parseOpoCutoff } from '../opo';

describe('parseOpoCutoff', () => {
  it('reads year and quarter', () => {
    expect(parseOpoCutoff('2026Q4')).toEqual({ year: 2026, quarter: 4 });
  });

  it('returns null for empty or malformed values', () => {
    expect(parseOpoCutoff(null)).toBeNull();
    expect(parseOpoCutoff('')).toBeNull();
    expect(parseOpoCutoff('2026')).toBeNull();
  });
});

describe('isOpoOff', () => {
  it('is false without a cutoff', () => {
    expect(isOpoOff(null, 2030, 1)).toBe(false);
  });

  it('is false before the cutoff quarter', () => {
    expect(isOpoOff('2026Q4', 2026, 3)).toBe(false);
    expect(isOpoOff('2026Q4', 2025, 4)).toBe(false);
  });

  it('is true from the cutoff quarter on', () => {
    expect(isOpoOff('2026Q4', 2026, 4)).toBe(true);
    expect(isOpoOff('2026Q4', 2027, 1)).toBe(true);
  });

  it('accepts Q-prefixed quarters', () => {
    expect(isOpoOff('2026Q4', 2026, 'Q4')).toBe(true);
    expect(isOpoOff('2026Q4', 2026, 'Q2')).toBe(false);
  });
});

describe('foldOpo', () => {
  it('moves ОПЭ hours into analyst and dev by ratio', () => {
    expect(foldOpo({ analyst: 10, dev: 20, qa: 5, opo: 8 }, 0.25)).toEqual({
      analyst: 12, dev: 26, qa: 5, opo: 0,
    });
  });

  it('splits in half when ratio is missing', () => {
    expect(foldOpo({ analyst: 0, dev: 0, qa: 0, opo: 10 }, null)).toEqual({
      analyst: 5, dev: 5, qa: 0, opo: 0,
    });
  });
});
