import { describe, it, expect } from 'vitest';
import { NAV_GROUPS, findGroupForPath } from '../navConfig';

describe('navConfig', () => {
  it('три группы в постоянном порядке: Обзор, Планирование, Данные', () => {
    expect(NAV_GROUPS.map((g) => g.label)).toEqual(['Обзор', 'Планирование', 'Данные']);
  });

  it('«Настройки» — только для администратора', () => {
    const settings = NAV_GROUPS.flatMap((g) => g.items).find((it) => it.key === '/settings');
    expect(settings?.adminOnly).toBe(true);
  });

  it('группа по адресу: точный пункт и вложенные страницы', () => {
    expect(findGroupForPath(NAV_GROUPS, '/')?.id).toBe('overview');
    expect(findGroupForPath(NAV_GROUPS, '/projects/ERP')?.id).toBe('overview');
    expect(findGroupForPath(NAV_GROUPS, '/analytics/work-type-report/print')?.id).toBe('overview');
    expect(findGroupForPath(NAV_GROUPS, '/resource-planning/compare')?.id).toBe('planning');
    expect(findGroupForPath(NAV_GROUPS, '/settings')?.id).toBe('data');
  });

  it('«/» не захватывает чужие адреса; неизвестный адрес — без группы', () => {
    expect(findGroupForPath(NAV_GROUPS, '/planning')?.id).toBe('planning');
    expect(findGroupForPath(NAV_GROUPS, '/admin/jira-migration')).toBeUndefined();
  });
});
