import { describe, it, expect } from 'vitest';
import {
  candidateLabel, candidateOptions, candidatesQueryKey, sameCandidatesTarget,
} from './rpCandidates';
import type { AssignmentCandidate, AssignmentOut } from '../api/resourcePlanning';

const c = (over: Partial<AssignmentCandidate>): AssignmentCandidate => ({
  employee_id: 'e1',
  display_name: 'Пряничников',
  role: 'dev',
  team: 'Команда 1С',
  load_pct: 42.4,
  ...over,
});

const ROLES = new Map([['dev', 'Программист']]);

describe('candidateLabel', () => {
  it('чужая команда видна в подписи, роль — по справочнику', () => {
    expect(candidateLabel(c({}), 'other', ROLES)).toBe('Пряничников · Программист · Команда 1С · 42%');
  });
  it('своя команда — без названия команды, с границами участия', () => {
    expect(candidateLabel(c({ member_to: '2026-08-10' }), 'team', ROLES)).toBe(
      'Пряничников · Программист · 42% (в команде по 10.08)',
    );
  });
  it('без роли или с ролью не из справочника — без служебного кода', () => {
    expect(candidateLabel(c({ role: null }), 'other', ROLES)).toBe('Пряничников · Команда 1С · 42%');
    expect(candidateLabel(c({ role: 'RP' }), 'other', ROLES)).toBe('Пряничников · Команда 1С · 42%');
  });
  it('кандидат фазы — свободные часы в даты фазы перед загрузкой', () => {
    expect(candidateLabel(c({ free_hours: 34.4, load_pct: 87 }), 'other', ROLES)).toBe(
      'Пряничников · Программист · Команда 1С · свободно 34 ч в даты фазы · 87%',
    );
    expect(candidateLabel(c({ free_hours: 0 }), 'team', ROLES)).toBe(
      'Пряничников · Программист · свободно 0 ч в даты фазы · 42%',
    );
  });
});

describe('candidateOptions', () => {
  it('группы AntD Select', () => {
    const opts = candidateOptions([
      { key: 'jira', label: 'Из Jira', employees: [c({})] },
    ], ROLES);
    expect(opts).toEqual([
      {
        label: 'Из Jira',
        title: 'Из Jira',
        options: [{ value: 'e1', label: 'Пряничников · Программист · Команда 1С · 42%' }],
      },
    ]);
  });
  it('занятый в соседней колонке — неактивен, с подсказкой', () => {
    const opts = candidateOptions([
      { key: 'other', label: 'Другие команды', employees: [c({}), c({ employee_id: 'e2', display_name: 'Иванов' })] },
    ], ROLES, { id: 'e1', hint: 'уже аналитик этой задачи' });
    expect(opts[0].options).toEqual([
      {
        value: 'e1',
        label: 'Пряничников · Программист · Команда 1С · 42% — уже аналитик этой задачи',
        disabled: true,
      },
      { value: 'e2', label: 'Иванов · Программист · Команда 1С · 42%' },
    ]);
  });
});

describe('sameCandidatesTarget', () => {
  const key = (plan: string, id: string, item: string, phase: AssignmentOut['phase']) =>
    candidatesQueryKey(plan, { id, backlog_item_id: item, phase });
  const shown = key('p1', 'a1', 'i1', 'dev');

  it('пересчёт пересоздал строку фазы с новым id — прежний список годится', () => {
    expect(sameCandidatesTarget(shown, key('p1', 'a2', 'i1', 'dev'))).toBe(true);
  });

  it('другая фаза, задача или план — прежний список не подставляется', () => {
    expect(sameCandidatesTarget(shown, key('p1', 'a3', 'i1', 'analyst'))).toBe(false);
    expect(sameCandidatesTarget(shown, key('p1', 'a4', 'i2', 'dev'))).toBe(false);
    expect(sameCandidatesTarget(shown, key('p2', 'a1', 'i1', 'dev'))).toBe(false);
  });
});
