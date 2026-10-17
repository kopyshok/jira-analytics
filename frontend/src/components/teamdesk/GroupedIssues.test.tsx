// @vitest-environment jsdom
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { DeskDeveloper, DeskIssue } from '../../api/teamDesk';
import { GroupedIssues, VIRTUAL_ROW_THRESHOLD } from './GroupedIssues';

const dev = (id: string): DeskDeveloper => ({
  developer_id: id, display_name: `Разработчик ${id}`, total_issues: 0, in_dev: 0,
  in_progress: 0, waiting: 0, todo: 0, est_hours: 0, fact_hours: 0, accuracy: null,
  flag_counts: {}, status_counts: {},
});

const issue = (n: number, developerId: string, extra: Partial<DeskIssue> = {}): DeskIssue => ({
  id: `i-${n}`, key: `OS-${n}`, summary: `Задача ${n}`, issue_type: 'Задача',
  status: 'В работе', status_group: 'dev', developer_id: developerId,
  developer_name: `Разработчик ${developerId}`, parent_id: null, est_hours: 8,
  fact_hours: 2, fact_by_person: [], alien_hours: 0, days_in_status: 3,
  is_analysis: false, is_subtask: false, is_standalone: true, assigned_to_owner: true,
  in_queue: true, daily_rate: null, sprint: null, sprints: [], release: null,
  flags: [], signatures: {}, reviewed: [],
  ...extra,
});

/** Подзадачи задачи i-0: в обоих наборах они есть и свёрнуты. */
const SUBTASKS = [
  issue(9001, 'a', { parent_id: 'i-0', is_subtask: true, summary: 'Подзадача 1' }),
  issue(9002, 'a', { parent_id: 'i-0', is_subtask: true, summary: 'Подзадача 2' }),
];

/**
 * Задачи поровну у двух разработчиков: чётные — у «a», нечётные — у «b».
 * Оценка разная, чтобы было что сортировать.
 */
function dataset(count: number): DeskIssue[] {
  return [
    ...Array.from({ length: count }, (_, n) =>
      issue(n, n % 2 ? 'b' : 'a', { est_hours: ((n * 37) % 97) + 1 })),
    ...SUBTASKS,
  ];
}

const DEVELOPERS = [dev('a'), dev('b')];
/** Ниже порога: все строки рисуются целиком. */
const SMALL = dataset(30);
/** Выше порога даже со свёрнутым первым разработчиком. */
const BIG = dataset(VIRTUAL_ROW_THRESHOLD * 3);

type Extra = Partial<React.ComponentProps<typeof GroupedIssues>>;

function renderDesk(issues: DeskIssue[], extra: Extra = {}) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <GroupedIssues
        title="Задачи"
        developers={DEVELOPERS}
        issues={issues}
        overrunPct={30}
        {...extra}
      />
    </QueryClientProvider>,
  );
}

/** Ключи строк, которые сейчас есть в разметке, — по порядку. */
const rowKeys = (container: HTMLElement): string[] =>
  Array.from(container.querySelectorAll('[data-row-key]')).map(
    (el) => el.getAttribute('data-row-key')!,
  );

const row = (container: HTMLElement, key: string): HTMLElement =>
  container.querySelector(`[data-row-key="${key}"]`) as HTMLElement;

const HINT = /Список большой/;

/** Заголовок колонки: в таблице с прокруткой вбок подписи повторяются в строке-замере. */
const headerCell = (container: HTMLElement, title: string): HTMLElement =>
  within(container.querySelector('.ant-table-thead') as HTMLElement).getByText(title).closest('th')!;

beforeAll(() => {
  // В jsdom нет ни запросов к размеру экрана, ни наблюдателя за размером.
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
  vi.restoreAllMocks();
});

describe('стол тимлида: список задач в «Все задачи»', () => {
  it('на тысячах задач рисует только видимые строки, счётчик — по всем', () => {
    const issues = Array.from({ length: 9000 }, (_, n) => issue(n, n % 2 ? 'b' : 'a'));
    const html = renderToStaticMarkup(
      <QueryClientProvider client={new QueryClient()}>
        <GroupedIssues title="Задачи" developers={DEVELOPERS} issues={issues} overrunPct={30} />
      </QueryClientProvider>,
    );
    const rows = (html.match(/data-row-key="/g) ?? []).length;
    expect(html).toContain('9000 задач');
    expect(rows).toBeGreaterThan(0);
    expect(rows).toBeLessThan(100);
  });
});

describe.each([
  ['обычный список (ниже порога)', SMALL, false],
  ['большой список (выше порога)', BIG, true],
] as const)('стол тимлида: %s', (_name, issues, virtual) => {
  const firstOfA = issues.filter((i) => i.developer_id === 'a' && !i.parent_id);

  it(virtual ? 'рисует только видимые строки и пишет подсказку' : 'рисует все строки, без подсказки', () => {
    const { container } = renderDesk(issues, { onDailyRate: () => {} });
    const shown = rowKeys(container);
    if (virtual) {
      expect(screen.getByText(HINT)).toBeTruthy();
      expect(container.querySelector('.ant-table-tbody-virtual')).not.toBeNull();
      expect(shown.length).toBeGreaterThan(0);
      expect(shown.length).toBeLessThan(100);
    } else {
      expect(screen.queryByText(HINT)).toBeNull();
      expect(container.querySelector('.ant-table-tbody-virtual')).toBeNull();
      // Все задачи в разметке — их находит поиск браузера, до полей DevForDay
      // доходит Tab.
      const topLevel = issues.filter((i) => !i.parent_id);
      topLevel.forEach((i) => expect(screen.getByText(i.key)).toBeTruthy());
      expect(screen.getAllByRole('spinbutton')).toHaveLength(topLevel.length);
      expect(shown).toHaveLength(topLevel.length + DEVELOPERS.length);
    }
  });

  it('клик по строке человека сворачивает и разворачивает его задачи', () => {
    const { container } = renderDesk(issues);
    expect(row(container, firstOfA[0].id)).not.toBeNull();
    fireEvent.click(row(container, 'group-a'));
    expect(row(container, firstOfA[0].id)).toBeNull();
    // Задачи второго человека поднялись вверх — их строка на экране.
    expect(row(container, 'group-b')).not.toBeNull();
    expect(screen.queryByText(HINT) != null).toBe(virtual);
    fireEvent.click(row(container, 'group-a'));
    expect(row(container, firstOfA[0].id)).not.toBeNull();
  });

  it('подзадачи свёрнуты и раскрываются по стрелке', () => {
    const { container } = renderDesk(issues);
    expect(row(container, 'i-9001')).toBeNull();
    const toggle = row(container, 'i-0').querySelector('.ant-table-row-expand-icon') as HTMLElement;
    fireEvent.click(toggle);
    expect(row(container, 'i-9001')).not.toBeNull();
    expect(row(container, 'i-9002')).not.toBeNull();
  });

  it('сортировка по оценке меняет порядок задач внутри человека', () => {
    const { container } = renderDesk(issues);
    fireEvent.click(headerCell(container, 'Оценка'));
    const expected = [...firstOfA]
      .sort((x, y) => (x.est_hours ?? 0) - (y.est_hours ?? 0))
      .slice(0, 5)
      .map((i) => i.id);
    const shown = rowKeys(container);
    const start = shown.indexOf('group-a') + 1;
    expect(shown.slice(start, start + 5)).toEqual(expected);
  });

  it('растягивание колонки — один вызов с шириной всех колонок', () => {
    // В jsdom у элементов нет размеров: каждая колонка на экране — 100 px.
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
      { width: 100, height: 20, top: 0, left: 0, right: 100, bottom: 20, x: 0, y: 0, toJSON: () => ({}) },
    );
    const onColumnWidthsChange = vi.fn();
    const { container } = renderDesk(issues, { onColumnWidthsChange });
    const th = headerCell(container, 'Статус');
    const handle = th.querySelector('span[style*="col-resize"]') as HTMLElement;
    fireEvent.mouseDown(handle, { clientX: 100 });
    fireEvent.mouseMove(document, { clientX: 120 });
    fireEvent.mouseMove(document, { clientX: 150 });
    expect(onColumnWidthsChange).not.toHaveBeenCalled();
    fireEvent.mouseUp(document);
    expect(onColumnWidthsChange).toHaveBeenCalledTimes(1);
    expect(onColumnWidthsChange).toHaveBeenCalledWith({
      task: 100, status: 200, sprint: 100, release: 100, est: 100,
      fact: 100, left: 100, scale: 100, days: 100, flags: 100,
    });
  });

  it('пустой срез — пустая таблица без подсказки', () => {
    // Отбор, под который не попала ни одна задача: строк нет — порог не превышен.
    const { container } = renderDesk(issues, { statusFilter: 'Нет такого статуса' });
    expect(rowKeys(container)).toEqual([]);
    expect(container.querySelector('.ant-table-placeholder')).not.toBeNull();
    expect(screen.queryByText(HINT)).toBeNull();
  });
});
