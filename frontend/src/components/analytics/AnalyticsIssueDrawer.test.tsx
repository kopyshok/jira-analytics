// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { IssueContextResponse } from '../../types/api';
import AnalyticsIssueDrawer from './AnalyticsIssueDrawer';

const base = {
  status: 'В работе', status_category: 'indeterminate', category: null,
  assigned_category: null, include_in_analysis: true, is_container: false,
  siblings_total: 1, subtree_count: 0,
};

/** Эпик → задача → подзадача; внутренние номера не похожи на ключи. */
const CONTEXTS: Record<string, IssueContextResponse> = {
  'uuid-epic': {
    ...base, id: 'uuid-epic', key: 'OS-1', summary: 'Эпик', issue_type: 'Эпик',
    ancestors: [], children: [],
  },
  'uuid-task': {
    ...base, id: 'uuid-task', key: 'OS-2', summary: 'Задача', issue_type: 'Задача',
    ancestors: [{ id: 'uuid-epic', key: 'OS-1', summary: 'Эпик', issue_type: 'Эпик' }],
    children: [{
      id: 'uuid-sub', key: 'OS-3', summary: 'Подзадача', status: 'Открыта',
      status_category: 'new', issue_type: 'Подзадача', category: null,
      assigned_category: null, include_in_analysis: true, subtree_count: 0,
    }],
  },
  'uuid-sub': {
    ...base, id: 'uuid-sub', key: 'OS-3', summary: 'Подзадача', issue_type: 'Подзадача',
    ancestors: [], children: [],
  },
};

vi.mock('../../hooks/useIssueContext', () => ({
  useIssueContext: (id: string) => ({
    data: CONTEXTS[id], isLoading: false, isError: false, refetch: () => {},
  }),
}));
vi.mock('../../hooks/useCategories', () => ({ useCategories: () => ({ items: [] }) }));
vi.mock('./IssueCategorizer', () => ({ default: () => null }));
vi.mock('./AnalyticsWorklogsBlock', () => ({ default: () => null }));
vi.mock('../shared/JiraIssueLink', () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <span data-testid="header-key">{children}</span>
  ),
}));

beforeAll(() => {
  window.matchMedia ??= ((query: string) => ({
    matches: false, media: query, onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
});

afterEach(cleanup);

async function openTask() {
  const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query');
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AnalyticsIssueDrawer
        issueId="uuid-task"
        issueKey="OS-2"
        periodStart="2026-10-01"
        periodEnd="2026-10-31"
        onClose={() => {}}
      />
    </QueryClientProvider>,
  );
}

const headerKey = () => screen.getByTestId('header-key').textContent;

describe('аналитика: карточка задачи', () => {
  it('переход на родителя — в заголовке ключ эпика, а не внутренний номер', async () => {
    await openTask();
    expect(headerKey()).toBe('OS-2');
    fireEvent.click(screen.getByText('OS-1'));
    expect(headerKey()).toBe('OS-1');
    fireEvent.click(screen.getByText('← назад'));
    expect(headerKey()).toBe('OS-2');
  });

  it('переход на подзадачу — в заголовке её ключ', async () => {
    await openTask();
    fireEvent.click(screen.getByText('OS-3'));
    expect(headerKey()).toBe('OS-3');
  });
});
