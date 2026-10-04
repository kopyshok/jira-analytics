import { describe, it, expect } from 'vitest';
import { groupScenarioOptions, isOutsideHeader, resolvePageTeam } from './rpTeams';

const sc = (id: string, team: string | null, name = id) => ({
  id, team, name, quarter: 'Q4', year: 2026,
});

describe('resolvePageTeam', () => {
  it('команда плана главнее остального', () => {
    expect(resolvePageTeam(['A', 'B'], 'B', 'A')).toBe('B');
  });
  it('нет плана — команда сценария из адреса', () => {
    expect(resolvePageTeam(['A', 'B'], null, 'B')).toBe('B');
  });
  it('ничего не выбрано — первая команда шапки', () => {
    expect(resolvePageTeam(['A', 'B'], null, null)).toBe('A');
  });
  it('шапка пуста — пустая команда', () => {
    expect(resolvePageTeam([], null, null)).toBe('');
  });
});

describe('isOutsideHeader', () => {
  it('команда плана не в шапке', () => {
    expect(isOutsideHeader(['A'], 'B')).toBe(true);
  });
  it('команда в шапке, команды нет или шапка пуста — не сбрасываем', () => {
    expect(isOutsideHeader(['A'], 'A')).toBe(false);
    expect(isOutsideHeader(['A'], null)).toBe(false);
    expect(isOutsideHeader([], 'B')).toBe(false);
  });
});

describe('groupScenarioOptions', () => {
  const list = [sc('1', 'B'), sc('2', 'A'), sc('3', 'B')];
  it('одна команда — плоский список без групп', () => {
    const o = groupScenarioOptions(list, ['B']);
    expect(o).toEqual([
      { label: 'Q4 2026 — 1', value: '1' },
      { label: 'Q4 2026 — 2', value: '2' },
      { label: 'Q4 2026 — 3', value: '3' },
    ]);
  });
  it('несколько команд — группы в порядке шапки, пустые не показываем', () => {
    const o = groupScenarioOptions(list, ['A', 'B', 'C']);
    expect(o).toEqual([
      { label: 'A', options: [{ label: 'Q4 2026 — 2', value: '2' }] },
      {
        label: 'B',
        options: [
          { label: 'Q4 2026 — 1', value: '1' },
          { label: 'Q4 2026 — 3', value: '3' },
        ],
      },
    ]);
  });
});
