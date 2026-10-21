// @vitest-environment jsdom
import { App } from 'antd';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { ProjectDetail } from '../../types/projects';

const copyText = vi.fn<(text: string) => Promise<boolean>>();
vi.mock('../../utils/clipboard', () => ({ copyText: (t: string) => copyText(t) }));
vi.mock('../../hooks/useProjectSummary', () => ({
  useRegenerateSummary: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('../shared/AiGate', () => ({ AiGate: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../shared/JiraIssueLink', () => ({ default: ({ issueKey }: { issueKey: string }) => <span>{issueKey}</span> }));

const { ProjectHeader } = await import('./ProjectHeader');

const detail = { key: 'RFA 7', summary: 'Проект', status: 'В работе', status_category: 'indeterminate' } as ProjectDetail;
const expectedUrl = `${window.location.origin}/projects/RFA%207`;

function renderHeader() {
  return render(
    <App>
      <ProjectHeader detail={detail} summary={null} view="analysis" onViewChange={() => {}} />
    </App>,
  );
}

/** Открыть меню «…» и нажать «Копировать ссылку». */
async function clickCopyLink(container: HTMLElement) {
  const more = container.querySelector('.anticon-more')!.closest('button')!;
  fireEvent.click(more);
  fireEvent.click(await screen.findByText('Копировать ссылку'));
}

beforeAll(() => {
  window.matchMedia ??= ((query: string) => ({
    matches: false, media: query, onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

afterEach(() => {
  cleanup();
  copyText.mockReset();
});

describe('карточка проекта: «Копировать ссылку»', () => {
  it('копирует ссылку на карточку и сообщает об этом', async () => {
    copyText.mockResolvedValue(true);
    const { container } = renderHeader();
    await clickCopyLink(container);
    await waitFor(() => expect(copyText).toHaveBeenCalledWith(expectedUrl));
    expect(await screen.findByText('Ссылка скопирована')).toBeTruthy();
  });

  it('буфер недоступен — показывает ссылку, чтобы скопировать вручную', async () => {
    copyText.mockResolvedValue(false);
    const { container } = renderHeader();
    await clickCopyLink(container);
    expect(await screen.findByDisplayValue(expectedUrl)).toBeTruthy();
    expect(screen.getByText(/Ctrl\+C/)).toBeTruthy();
  });
});
