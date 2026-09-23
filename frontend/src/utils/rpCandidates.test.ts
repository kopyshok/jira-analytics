import { describe, it, expect } from 'vitest';
import { candidateLabel, candidateOptions } from './rpCandidates';
import type { AssignmentCandidate } from '../api/resourcePlanning';

const c = (over: Partial<AssignmentCandidate>): AssignmentCandidate => ({
  employee_id: 'e1',
  display_name: 'Пряничников',
  role: 'developer',
  team: 'Команда 1С',
  load_pct: 42.4,
  ...over,
});

describe('candidateLabel', () => {
  it('чужая команда видна в подписи', () => {
    expect(candidateLabel(c({}), 'other')).toBe('Пряничников · Команда 1С · 42%');
  });
  it('своя команда — без названия команды, с границами участия', () => {
    expect(candidateLabel(c({ member_to: '2026-08-10' }), 'team')).toBe(
      'Пряничников · 42% (в команде по 10.08)',
    );
  });
});

describe('candidateOptions', () => {
  it('группы AntD Select', () => {
    const opts = candidateOptions([
      { key: 'jira', label: 'Из Jira', employees: [c({})] },
    ]);
    expect(opts).toEqual([
      {
        label: 'Из Jira',
        title: 'Из Jira',
        options: [{ value: 'e1', label: 'Пряничников · Команда 1С · 42%' }],
      },
    ]);
  });
});
