import { describe, expect, it } from 'vitest';
import type { TimelineRow } from '../../../types/projects';
import { legendPhases } from './phaseLegend';

const bar = (phase: string, label: string) => ({
  phase, label, start_date: '2026-10-01', end_date: '2026-10-10',
});
const row = (...bars: ReturnType<typeof bar>[]): TimelineRow => ({
  key: 'RFA-1', title: 'Проект', status: null, bars,
});

describe('легенда таймлайна проекта', () => {
  it('без ОПЭ на шкале — ОПЭ в легенде нет', () => {
    const rows = [row(bar('dev', 'Разработка'), bar('analyst', 'Анализ'), bar('qa', 'Тестирование'))];
    expect(legendPhases(rows).map((p) => p.label)).toEqual(['Анализ', 'Разработка', 'Тестирование']);
  });

  it('фазы из всех строк, без повторов, в порядке работ', () => {
    const rows = [
      row(bar('opo', 'ОПЭ'), bar('dev', 'Разработка')),
      row(bar('dev', 'Разработка'), bar('cons', 'Консультация')),
    ];
    expect(legendPhases(rows).map((p) => p.code)).toEqual(['cons', 'dev', 'opo']);
  });

  it('у каждой фазы свой цвет полосы', () => {
    const [opo] = legendPhases([row(bar('opo', 'ОПЭ'))]);
    expect(opo.color).toBe('var(--wt-opo, #7F77DD)');
  });
});
