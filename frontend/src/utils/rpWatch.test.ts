import { describe, expect, it } from 'vitest';
import { freeByMonthLabel, roleTeamPicks, techReserveText } from './rpWatch';
import type { EmployeeResponse } from '../types/api';
import type { ReserveTypeRow } from '../api/resourcePlanning';

const emp = (over: Partial<EmployeeResponse>): EmployeeResponse => ({
  id: 'e1', jira_account_id: 'a', display_name: 'Иванов', email: null, avatar_url: null,
  is_active: true, role: 'dev', team: 'ERP', ...over,
});

describe('roleTeamPicks', () => {
  const list = [
    emp({ id: 'e1', teams: [{ team: 'ERP', is_primary: true }] }),
    emp({ id: 'e2', role: 'analyst', teams: [{ team: 'ERP', is_primary: true }] }),
    // В ERP вторая команда — тоже «в команде».
    emp({ id: 'e3', team: 'Блок', teams: [{ team: 'Блок', is_primary: true }, { team: 'ERP', is_primary: false }] }),
    // Выбыл из ERP до даты — не в команде.
    emp({ id: 'e4', teams: [{ team: 'ERP', is_primary: true, left_at: '2026-09-01' }] }),
    // Придёт позже — ещё не в команде.
    emp({ id: 'e5', teams: [{ team: 'ERP', is_primary: true, joined_at: '2026-11-01' }] }),
    emp({ id: 'e6', is_active: false, teams: [{ team: 'ERP', is_primary: true }] }),
    // Без списка команд — по основной команде.
    emp({ id: 'e7' }),
  ];
  it('все активные сотрудники роли, состоящие в команде на дату', () => {
    expect(roleTeamPicks(list, 'ERP', 'dev', '2026-10-04')).toEqual(['e1', 'e3', 'e7']);
  });
  it('нет команды или роли — пусто', () => {
    expect(roleTeamPicks(list, '', 'dev', '2026-10-04')).toEqual([]);
    expect(roleTeamPicks(list, 'ERP', '', '2026-10-04')).toEqual([]);
  });
});

describe('freeByMonthLabel', () => {
  it('месяцы квартала коротко, часы с округлением', () => {
    expect(freeByMonthLabel([
      { month: '2026-10-01', hours: 40.4 },
      { month: '2026-11-01', hours: 0 },
      { month: '2026-12-01', hours: 12.06 },
    ])).toBe('окт 40,4 · ноя 0 · дек 12,1');
  });
});

describe('techReserveText', () => {
  const row = (over: Partial<ReserveTypeRow>): ReserveTypeRow => ({
    work_type_id: 'wt', label: 'Технические задачи', planned_hours: 100, blocked_hours: 0,
    other_teams_hours: 80, remaining_hours: 20, overuse_hours: 0, ...over,
  });
  it('остаток или перерасход', () => {
    expect(techReserveText(row({}))).toEqual({ text: 'осталось 20 ч', over: false });
    expect(techReserveText(row({ other_teams_hours: 130, remaining_hours: 0, overuse_hours: 30 }))).toEqual({
      text: 'сверх запаса 30 ч', over: true,
    });
    expect(techReserveText(null)).toEqual({ text: '—', over: false });
  });
});
