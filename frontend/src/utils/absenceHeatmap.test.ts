import { describe, expect, it } from 'vitest';
import type { AbsenceResponse } from '../types/api';
import { absenceCellsByEmployee, absenceCellTip, quarterDays } from './absenceHeatmap';

const abs = (id: string, employee_id: string, start_date: string, end_date: string, label = 'Отпуск'): AbsenceResponse => ({
  id, employee_id, start_date, end_date,
  reason_id: 'r', reason_code: 'vac', reason_label: label, reason_is_planned: true,
  reason_color: '#123456', hours_total: null,
});

describe('дни квартала для карты отсутствий', () => {
  const days = quarterDays(2026, 4);

  it('все дни квартала подряд', () => {
    expect(days).toHaveLength(92);
    expect(days[0].iso).toBe('2026-10-01');
    expect(days[91].iso).toBe('2026-12-31');
  });

  it('выходные и граница месяца (кроме первого месяца квартала)', () => {
    const byIso = new Map(days.map((d) => [d.iso, d]));
    expect(byIso.get('2026-10-03')!.weekend).toBe(true);  // суббота
    expect(byIso.get('2026-10-05')!.weekend).toBe(false); // понедельник
    expect(byIso.get('2026-10-01')!.monthStart).toBe(false);
    expect(byIso.get('2026-11-01')!.monthStart).toBe(true);
    expect(byIso.get('2026-12-01')!.monthStart).toBe(true);
    expect(days.filter((d) => d.label !== '').map((d) => d.label).slice(0, 4)).toEqual([1, 5, 10, 15]);
  });

  it('неизвестный квартал — пусто', () => {
    expect(quarterDays(2026, 7)).toEqual([]);
  });
});

describe('клетки отсутствий по сотрудникам', () => {
  const days = quarterDays(2026, 4);

  it('отсутствие обрезается границами квартала, вне квартала — не попадает', () => {
    const cells = absenceCellsByEmployee([
      abs('a1', 'e1', '2026-09-28', '2026-10-02'),
      abs('a2', 'e1', '2026-07-01', '2026-07-10'),
      abs('a3', 'e2', '2026-12-30', '2027-01-05'),
    ], days);
    const e1 = cells.get('e1')!;
    expect(e1.slice(0, 3).map((a) => a?.id)).toEqual(['a1', 'a1', undefined]);
    expect(e1.filter(Boolean)).toHaveLength(2);
    const e2 = cells.get('e2')!;
    expect(e2.filter(Boolean).map((a) => a!.id)).toEqual(['a3', 'a3']);
    expect(e2[90]?.id).toBe('a3');
  });

  it('пересечение — день за первым отсутствием в списке, как раньше', () => {
    const cells = absenceCellsByEmployee([
      abs('first', 'e1', '2026-10-10', '2026-10-12'),
      abs('second', 'e1', '2026-10-11', '2026-10-14'),
    ], days);
    const row = cells.get('e1')!;
    expect(row.slice(9, 14).map((a) => a?.id)).toEqual(['first', 'first', 'first', 'second', 'second']);
  });

  it('у сотрудника без отсутствий в квартале строки нет', () => {
    expect(absenceCellsByEmployee([abs('a', 'e1', '2026-01-01', '2026-01-02')], days).has('e1')).toBe(false);
  });
});

describe('подсказка клетки', () => {
  const day = quarterDays(2026, 4)[4]; // 05.10

  it('день отсутствия — причина и период', () => {
    expect(absenceCellTip('Иванов', day, abs('a', 'e', '2026-10-03', '2026-10-09', 'Больничный')))
      .toBe('Иванов: Больничный, 03.10–09.10');
  });

  it('обычный день — имя и дата', () => {
    expect(absenceCellTip('Иванов', day, undefined)).toBe('Иванов · 05.10');
  });
});
