import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import AnalyticsWorklogsBlock from './AnalyticsWorklogsBlock';

vi.mock('../../hooks/useIssueWorklogs', () => ({
  useIssueWorklogs: () => ({
    isLoading: false,
    data: [
      { worklog_id: 'w1', started_at: '2026-07-01T10:00:00', hours: 1, employee_id: 'e1', employee_name: 'Медведева', comment: 'своё' },
      { worklog_id: 'w2', started_at: '2026-07-02T10:00:00', hours: 2, employee_id: 'e2', employee_name: 'Пак', comment: 'чужое' },
    ],
  }),
}));

const render = (employee?: { id: string; name: string }) =>
  renderToStaticMarkup(
    <AnalyticsWorklogsBlock issueId="i1" periodStart="2026-07-01" periodEnd="2026-09-30" employee={employee} />,
  );

describe('ворклоги задачи в карточке Аналитики', () => {
  it('из строки сотрудника — сразу только его ворклоги', () => {
    const html = render({ id: 'e1', name: 'Медведева' });
    expect(html).toContain('своё');
    expect(html).not.toContain('чужое');
    expect(html).toContain('1 из 2');
  });

  it('без сотрудника — все ворклоги и без переключателя', () => {
    const html = render();
    expect(html).toContain('своё');
    expect(html).toContain('чужое');
    expect(html).not.toContain('Только');
  });
});
