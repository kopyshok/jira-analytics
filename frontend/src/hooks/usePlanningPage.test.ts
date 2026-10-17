import { describe, expect, it } from 'vitest';
import { GRID, GRID_GAP, gridMinWidth } from './usePlanningPage';
import { getRoleTextColor, roleChipColors } from '../utils/roles';

describe('gridMinWidth', () => {
  it('сумма колонок, зазоров и полей строки', () => {
    expect(gridMinWidth('10px 20px minmax(30px, 1fr)')).toBe(10 + 20 + 30 + 2 * GRID_GAP + 32);
    expect(gridMinWidth(GRID)).toBeGreaterThan(1000);
  });
});

describe('цвета ролей без скина', () => {
  it('текст и плашка — как в справочнике', () => {
    const roles = [{ code: 'qa', label: 'Тестировщик', color: '#f48bc4', is_active: true }] as never;
    expect(getRoleTextColor(roles, 'qa')).toBe('#f48bc4');
    expect(roleChipColors('#f48bc4', '#00202a')).toEqual({ bg: '#f48bc4', fg: '#00202a' });
  });
});
