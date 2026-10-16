import { describe, it, expect } from 'vitest';
import type { DeskDeveloper, DeskIssue } from '../../api/teamDesk';
import { accuracyLevel, developerSeverity, rubberLeft, rubberToQueue } from './deskSignals';

describe('accuracyLevel', () => {
  it('перебор, недобор, норма, нет данных', () => {
    expect(accuracyLevel(1.31)).toBe('bad');
    expect(accuracyLevel(0.69)).toBe('warn');
    expect(accuracyLevel(1)).toBe('good');
    expect(accuracyLevel(null)).toBeNull();
  });
});

describe('developerSeverity', () => {
  const dev = (flags: DeskDeveloper['flag_counts']) => ({ flag_counts: flags }) as DeskDeveloper;
  it('перерасход важнее декомпозиции и зависания', () => {
    expect(developerSeverity(dev({ over: 1, decomp: 2 }))).toBe(2);
    expect(developerSeverity(dev({ decomp: 1 }))).toBe(1);
    expect(developerSeverity(dev({ stale: 1 }))).toBe(1);
    expect(developerSeverity(dev({ noest: 3 }))).toBe(0);
  });
});

describe('резиновые задачи', () => {
  const issue = (est: number | null, fact: number, rate: number | null) =>
    ({ est_hours: est, fact_hours: fact, daily_rate: rate }) as DeskIssue;

  it('остаток — оценка минус факт, не меньше нуля', () => {
    expect(rubberLeft(issue(40, 12, 4))).toBe(28);
    expect(rubberLeft(issue(10, 12, 4))).toBe(0);
    expect(rubberLeft(issue(null, 12, 4))).toBeNull();
  });

  it('в очередь — норма за дни, но не больше остатка', () => {
    expect(rubberToQueue(issue(40, 12, 4), 5)).toBe(20);
    expect(rubberToQueue(issue(40, 30, 4), 5)).toBe(10);
    expect(rubberToQueue(issue(null, 0, 4), 5)).toBe(20);
  });
});
