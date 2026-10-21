// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { DeskIssue } from '../../api/teamDesk';
import { RubberTasks } from './RubberTasks';

const rubber: DeskIssue = {
  id: 'i-1', key: 'OS-1', summary: 'Сопровождение', issue_type: 'Задача',
  status: 'В работе', status_group: 'dev', developer_id: 'a',
  developer_name: 'Разработчик a', parent_id: null, est_hours: 40,
  fact_hours: 2, fact_by_person: [], alien_hours: 0, days_in_status: 3,
  is_analysis: false, is_subtask: false, is_standalone: true, assigned_to_owner: true,
  in_queue: true, daily_rate: 2, sprint: null, sprints: [], release: null,
  flags: [], signatures: {}, reviewed: [],
};

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

/** Норма на экране меняется только после ответа сервера — здесь его нет. */
function renderRubber() {
  const onDailyRate = vi.fn();
  render(<RubberTasks issues={[rubber]} rubberDays={5} onDailyRate={onDailyRate} />);
  return { onDailyRate, input: screen.getByRole('spinbutton') };
}

describe('стол тимлида: дневная норма резиновой задачи', () => {
  it('Enter и следующая за ним потеря фокуса — одно сохранение', () => {
    const { onDailyRate, input } = renderRubber();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: '3' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.blur(input);
    expect(onDailyRate).toHaveBeenCalledTimes(1);
    expect(onDailyRate).toHaveBeenCalledWith('i-1', 3);
  });

  it('пока набирают, не сохраняет; уход из поля — одно сохранение итога', () => {
    const { onDailyRate, input } = renderRubber();
    fireEvent.focus(input);
    for (const text of ['1', '1.', '1.5']) {
      fireEvent.change(input, { target: { value: text } });
    }
    expect(onDailyRate).not.toHaveBeenCalled();
    fireEvent.blur(input);
    expect(onDailyRate).toHaveBeenCalledTimes(1);
    expect(onDailyRate).toHaveBeenCalledWith('i-1', 1.5);
  });

  it('значение за пределом сохраняется приведённым, один раз', () => {
    const { onDailyRate, input } = renderRubber();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: '30' } });
    fireEvent.blur(input);
    expect(onDailyRate).toHaveBeenCalledTimes(1);
    expect(onDailyRate).toHaveBeenCalledWith('i-1', 24);
  });

  it('без правки уход из поля ничего не сохраняет', () => {
    const { onDailyRate, input } = renderRubber();
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.blur(input);
    expect(onDailyRate).not.toHaveBeenCalled();
  });

  it('очистка поля снимает норму', () => {
    const { onDailyRate, input } = renderRubber();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: '' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onDailyRate).toHaveBeenCalledTimes(1);
    expect(onDailyRate).toHaveBeenCalledWith('i-1', null);
  });
});
