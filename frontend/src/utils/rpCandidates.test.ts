import { describe, it, expect } from 'vitest';
import { candidateLabel, candidateOptions } from './rpCandidates';
import type { AssignmentCandidate } from '../api/resourcePlanning';

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
});
