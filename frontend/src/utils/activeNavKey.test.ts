import { describe, expect, it } from 'vitest';
import { activeNavKey } from './activeNavKey';

const KEYS = [
  '/', '/projects', '/analytics', '/analytics/work-type-report', '/executive',
  '/capacity', '/planning', '/resource-planning', '/settings',
];

describe('пункт бокового меню для текущей страницы', () => {
  it('страница раздела — сам раздел', () => {
    expect(activeNavKey('/capacity', KEYS)).toBe('/capacity');
    expect(activeNavKey('/resource-planning', KEYS)).toBe('/resource-planning');
  });

  it('вложенная страница подсвечивает свой раздел', () => {
    expect(activeNavKey('/resource-planning/compare', KEYS)).toBe('/resource-planning');
    expect(activeNavKey('/projects/ABC', KEYS)).toBe('/projects');
    expect(activeNavKey('/capacity/', KEYS)).toBe('/capacity');
  });

  it('из вложенных разделов берётся самый точный', () => {
    expect(activeNavKey('/analytics', KEYS)).toBe('/analytics');
    expect(activeNavKey('/analytics/work-type-report', KEYS)).toBe('/analytics/work-type-report');
    expect(activeNavKey('/analytics/work-type-report/print', KEYS)).toBe('/analytics/work-type-report');
  });

  it('дашборд — только сама главная', () => {
    expect(activeNavKey('/', KEYS)).toBe('/');
    expect(activeNavKey('/unknown', KEYS)).toBeNull();
  });

  it('похожее начало адреса — не вложенность', () => {
    expect(activeNavKey('/planning-old', KEYS)).toBeNull();
    expect(activeNavKey('/resource-planningX', KEYS)).toBeNull();
  });
});
