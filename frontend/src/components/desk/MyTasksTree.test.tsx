import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ChildRow } from './MyTasksWidget';
import type { ProjectChild } from '../../types/desk';

const leaf: ProjectChild = {
  key: 'ITL-4', title: 'Лист', jira_url: 'https://j/ITL-4', status: 'Done',
  status_category: 'done', assignee: null, fact_hours: 3, children: [],
};
const mid: ProjectChild = {
  key: 'ITL-3', title: 'Середина', jira_url: 'https://j/ITL-3', status: 'In Progress',
  status_category: 'indeterminate', assignee: 'Иван', fact_hours: 3,
  children: [leaf],
};

describe('дерево «Мои задачи»', () => {
  it('уровень свёрнут по умолчанию: видна только своя строка, дети скрыты', () => {
    const html = renderToStaticMarkup(<ChildRow c={mid} />);
    expect(html).toContain('ITL-3');
    expect(html).toContain('Иван');
    expect(html).toContain('href="https://j/ITL-3"');
    expect(html).not.toContain('ITL-4');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('<button');
    expect(html).not.toContain('estimate');
  });

  it('закрытая задача приглушена, у листа стрелки нет', () => {
    const html = renderToStaticMarkup(<ChildRow c={leaf} depth={2} />);
    expect(html).toContain('desk-child-done');
    expect(html).toContain('hidden');
    expect(html).not.toContain('aria-expanded');
    expect(html).toContain('padding-left:36px');
  });
});
