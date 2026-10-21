import { describe, expect, it } from 'vitest';
import { resolveTourStep } from './tourTarget';
import { TOURS, type TourStepDef } from './tours';

const step: TourStepDef = {
  target: 'main',
  title: 'Основной',
  description: 'про основной',
  otherwise: { target: 'alt', title: 'Запасной', description: 'про запасной' },
};
const present = (...ids: string[]) => (id: string) => ids.includes(id);

describe('resolveTourStep', () => {
  it('цель шага на странице — основной шаг', () => {
    expect(resolveTourStep(step, present('main', 'alt'))).toEqual({ target: 'main', title: 'Основной', description: 'про основной' });
  });
  it('цели нет, есть запасная — шаг про запасную', () => {
    expect(resolveTourStep(step, present('alt'))).toEqual({ target: 'alt', title: 'Запасной', description: 'про запасной' });
  });
  it('нет ни той, ни другой — основной шаг (окно по центру)', () => {
    expect(resolveTourStep(step, present())).toEqual({ target: 'main', title: 'Основной', description: 'про основной' });
  });
});

describe('экскурсия по Сценариям', () => {
  it('шаг «Утвердить» у утверждённого сценария ведёт на «В черновик»', () => {
    const approve = TOURS.planning.steps.find(s => s.target === 'planning-approve')!;
    const view = resolveTourStep(approve, present('planning-revert'));
    expect(view.target).toBe('planning-revert');
    expect(view.title).toBe('Сценарий утверждён');
  });
});
