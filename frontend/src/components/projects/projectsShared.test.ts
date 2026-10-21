import { describe, it, expect } from 'vitest';
import type { ProjectListItem } from '../../types/projects';
import { avgProjectRating, pluralProjects, projectQueryParams } from './projectsShared';

describe('projectQueryParams', () => {
  it('пустые отборы не уходят в запрос', () => {
    expect(projectQueryParams({ search: '', statusCategory: '', category: '', year: 2026, quarter: 4 })).toEqual({
      search: undefined, status_category: undefined, category: undefined, year: 2026, quarter: 4,
    });
  });
  it('заданные — уходят под именами сервера', () => {
    expect(projectQueryParams({ search: 'ERP', statusCategory: 'done', category: 'archive_target', year: 2025, quarter: 1 }))
      .toMatchObject({ search: 'ERP', status_category: 'done', category: 'archive_target' });
  });
});

describe('avgProjectRating', () => {
  const item = (q: number | null, s: number | null, r: number | null) =>
    ({ rating_quality: q, rating_speed: s, rating_result: r }) as ProjectListItem;
  it('среднее только по заданным оценкам', () => {
    expect(avgProjectRating(item(4, null, 5))).toBe(5);
    expect(avgProjectRating(item(3, 4, 5))).toBe(4);
  });
  it('нет оценок — null', () => {
    expect(avgProjectRating(item(null, null, null))).toBeNull();
  });
});

describe('pluralProjects', () => {
  it.each([[1, 'проект'], [3, 'проекта'], [5, 'проектов'], [11, 'проектов'], [21, 'проект'], [24, 'проекта']])(
    '%i → %s', (n, word) => expect(pluralProjects(n)).toBe(word),
  );
});
