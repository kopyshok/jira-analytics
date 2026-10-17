import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import type { DeskDeveloper, DeskIssue } from '../../api/teamDesk';
import { GroupedIssues } from './GroupedIssues';

const dev = (id: string): DeskDeveloper => ({
  developer_id: id, display_name: `Разработчик ${id}`, total_issues: 0, in_dev: 0,
  in_progress: 0, waiting: 0, todo: 0, est_hours: 0, fact_hours: 0, accuracy: null,
  flag_counts: {}, status_counts: {},
});

const issue = (n: number, developerId: string): DeskIssue => ({
  id: `i-${n}`, key: `OS-${n}`, summary: `Задача ${n}`, issue_type: 'Задача',
  status: 'В работе', status_group: 'dev', developer_id: developerId,
  developer_name: `Разработчик ${developerId}`, parent_id: null, est_hours: 8,
  fact_hours: 2, fact_by_person: [], alien_hours: 0, days_in_status: 3,
  is_analysis: false, is_subtask: false, is_standalone: true, assigned_to_owner: true,
  in_queue: true, daily_rate: null, sprint: null, sprints: [], release: null,
  flags: [], signatures: {}, reviewed: [],
});

function render(issues: DeskIssue[], developers: DeskDeveloper[]): string {
  return renderToStaticMarkup(
    <QueryClientProvider client={new QueryClient()}>
      <GroupedIssues title="Задачи" developers={developers} issues={issues} overrunPct={30} />
    </QueryClientProvider>,
  );
}

describe('стол тимлида: список задач в «Все задачи»', () => {
  it('на тысячах задач рисует только видимые строки, счётчик — по всем', () => {
    const developers = [dev('a'), dev('b')];
    const issues = Array.from({ length: 9000 }, (_, n) => issue(n, n % 2 ? 'b' : 'a'));
    const html = render(issues, developers);
    const rows = (html.match(/data-row-key="/g) ?? []).length;
    expect(html).toContain('9000 задач');
    expect(rows).toBeGreaterThan(0);
    expect(rows).toBeLessThan(100);
  });
});
