import { describe, expect, it } from 'vitest';
import type { OnboardingStatus, StepState, StepStatus } from '../api/onboarding';
import { INTRO_STEPS, isClosed, progress, SETUP_STEPS, type SetupStep } from './steps';

function stepStatus(state: StepState): StepStatus {
  return { state, source: null, marked_by: null, marked_at: null };
}

function makeStatus(steps: Record<string, StepState>, completedTours: string[] = []): OnboardingStatus {
  const entries = Object.fromEntries(Object.entries(steps).map(([id, state]) => [id, stepStatus(state)]));
  return {
    team: 'demo',
    steps: entries,
    me: { completed_tours: completedTours, auto_opened: true, hidden: false },
  };
}

describe('isClosed — лист', () => {
  const leaf: SetupStep = { id: 'leaf', title: 'Лист', hint: '' };

  it('done — закрыт', () => {
    expect(isClosed(leaf, makeStatus({ leaf: 'done' }))).toBe(true);
  });

  it('skipped — закрыт', () => {
    expect(isClosed(leaf, makeStatus({ leaf: 'skipped' }))).toBe(true);
  });

  it('pending — не закрыт', () => {
    expect(isClosed(leaf, makeStatus({ leaf: 'pending' }))).toBe(false);
  });

  it('нет отметки на сервере — не закрыт', () => {
    expect(isClosed(leaf, makeStatus({}))).toBe(false);
  });

  it('статус ещё не загружен — не закрыт', () => {
    expect(isClosed(leaf, undefined)).toBe(false);
  });
});

describe('isClosed — группа', () => {
  const group: SetupStep = {
    id: 'group', title: 'Группа', hint: '',
    children: [
      { id: 'a', title: 'A', hint: '' },
      { id: 'b', title: 'B', hint: '' },
    ],
  };

  it('все подпункты закрыты (done + skipped) — группа закрыта', () => {
    expect(isClosed(group, makeStatus({ a: 'done', b: 'skipped' }))).toBe(true);
  });

  it('часть подпунктов ещё pending — группа не закрыта', () => {
    expect(isClosed(group, makeStatus({ a: 'done', b: 'pending' }))).toBe(false);
  });
});

describe('progress', () => {
  // «header» и «dashboard» из INTRO_STEPS пройдены; из SETUP_STEPS закрыты
  // «issues_loaded» (done) и «categorization» (skipped), «scenario» — группа
  // с непройденными подпунктами, остальные — pending.
  const status = makeStatus(
    { issues_loaded: 'done', categorization: 'skipped' },
    ['header', 'dashboard'],
  );

  it('без выбранной команды — считает только экскурсии знакомства', () => {
    expect(progress(status, false)).toEqual({ done: 2, total: INTRO_STEPS.length });
  });

  it('с выбранной командой — добавляет закрытые шаги настройки', () => {
    expect(progress(status, true)).toEqual({
      done: 2 + 2,
      total: INTRO_STEPS.length + SETUP_STEPS.length,
    });
  });

  it('ничего не пройдено — done 0', () => {
    expect(progress(makeStatus({}), true)).toEqual({ done: 0, total: INTRO_STEPS.length + SETUP_STEPS.length });
  });

  it('статус не загружен — total считается, done 0', () => {
    expect(progress(undefined, true)).toEqual({ done: 0, total: INTRO_STEPS.length + SETUP_STEPS.length });
  });
});
