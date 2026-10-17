import { describe, expect, it } from 'vitest';
import type { DeskDeveloper, DeskIssue } from '../api/teamDesk';
import { deskTaskCount, developersWord, tasksWord, teamAccuracy } from './deskSummary';

const issue = (over: Partial<DeskIssue>): DeskIssue => ({
  id: Math.random().toString(36), key: 'K-1', summary: '', issue_type: 'Задача', status: 'В работе',
  status_group: 'dev', developer_id: 'd', developer_name: 'Д', parent_id: null,
  est_hours: 10, fact_hours: 10, fact_by_person: [], alien_hours: 0, days_in_status: 0,
  is_analysis: false, is_subtask: false, is_standalone: true, assigned_to_owner: true,
  in_queue: false, daily_rate: null, sprint: null, sprints: [], release: null,
  flags: [], signatures: {}, reviewed: [],
  ...over,
});

describe('deskSummary', () => {
  it('teamAccuracy: медиана факт/оценка по самостоятельным задачам с оценкой и списаниями', () => {
    expect(teamAccuracy([
      issue({ est_hours: 10, fact_hours: 5 }),   // 0.5
      issue({ est_hours: 10, fact_hours: 10 }),  // 1.0
      issue({ est_hours: 10, fact_hours: 30 }),  // 3.0
      issue({ est_hours: null, fact_hours: 8 }),  // нет оценки — мимо
      issue({ est_hours: 10, fact_hours: 0 }),    // нет списаний — мимо
      issue({ est_hours: 10, fact_hours: 40, is_standalone: false }), // подзадача — мимо
    ])).toBe(1);
    expect(teamAccuracy([issue({ est_hours: 10, fact_hours: 5 }), issue({ est_hours: 10, fact_hours: 15 })])).toBe(1);
    expect(teamAccuracy([])).toBeNull();
  });

  it('deskTaskCount: сумма задач по людям', () => {
    expect(deskTaskCount([{ total_issues: 3 }, { total_issues: 4 }] as DeskDeveloper[])).toBe(7);
  });

  it('склонения', () => {
    expect([1, 2, 5, 11, 21, 24].map(developersWord)).toEqual(
      ['разработчик', 'разработчика', 'разработчиков', 'разработчиков', 'разработчик', 'разработчика'],
    );
    expect([1, 3, 25].map(tasksWord)).toEqual(['задача', 'задачи', 'задач']);
  });
});
