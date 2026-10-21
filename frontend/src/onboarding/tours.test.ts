import { describe, expect, it } from 'vitest';
import { INTRO_STEPS } from './steps';
import { TOURS } from './tours';

// Дерево Аналитики строится по «Настройке отчёта» пользователя: перечисленный
// раз и навсегда порядок уровней («Команда → роль → …») у многих не совпадает
// с тем, что на экране.
describe('онбординг Аналитики: уровни дерева', () => {
  it('шаг экскурсии «Отчёт» отсылает к «Настройке отчёта», а не перечисляет уровни', () => {
    const step = TOURS.analytics.steps.find((s) => s.target === 'analytics-table')!;
    expect(step.description).not.toContain('→');
    expect(step.description).toContain('«Настройк');
  });

  it('подсказка в «Первых шагах» не перечисляет уровни', () => {
    const intro = INTRO_STEPS.find((s) => s.tourId === 'analytics')!;
    expect(intro.hint).not.toContain('→');
  });
});
