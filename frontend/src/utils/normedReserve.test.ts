import { describe, expect, it } from 'vitest';
import { fmtHours, overuseCount, overuseLabel } from './normedReserve';
import type { ReserveOut } from '../api/resourcePlanning';

const reserve: ReserveOut = {
  team: 'ERP',
  scenario_name: 'Сценарий Q1',
  roles: [
    {
      role: 'dev',
      role_label: 'Разработчик',
      rows: [
        {
          work_type_id: 'wt1', label: 'Технические задачи',
          planned_hours: 102, blocked_hours: 0, other_teams_hours: 180,
          remaining_hours: 0, overuse_hours: 78,
        },
        {
          work_type_id: 'wt2', label: 'Орг. вопросы',
          planned_hours: 50, blocked_hours: 0, other_teams_hours: 0,
          remaining_hours: 49.8, overuse_hours: 0.2,
        },
      ],
    },
  ],
  other_team_work: [],
  work_types: [],
};

describe('overuseCount', () => {
  it('нет запаса — 0', () => {
    expect(overuseCount(null)).toBe(0);
    expect(overuseCount(undefined)).toBe(0);
  });
  it('считает строки с перерасходом больше 0,5 ч', () => {
    expect(overuseCount(reserve)).toBe(1);
  });
});

describe('overuseLabel', () => {
  it('нет перерасхода — null', () => {
    expect(overuseLabel(null)).toBeNull();
    expect(overuseLabel({ ...reserve, roles: [] })).toBeNull();
  });
  it('склоняет «вид» по числу строк с перерасходом', () => {
    expect(overuseLabel(reserve)).toBe('перерасход: 1 вид работ');
    const two: ReserveOut = {
      ...reserve,
      roles: [
        { ...reserve.roles[0] },
        { ...reserve.roles[0], role: 'analyst', role_label: 'Аналитик' },
      ],
    };
    expect(overuseLabel(two)).toBe('перерасход: 2 вида работ');
  });
});

describe('fmtHours', () => {
  it('округляет до десятых и подписывает часы', () => {
    expect(fmtHours(101.6)).toBe('101,6 ч');
    expect(fmtHours(0)).toBe('0 ч');
  });
});
