import { describe, expect, it } from 'vitest';
import { quarterWeeks, weekMonthSpans } from '../quarterWeeks';

describe('quarterWeeks', () => {
  it('Q4 2026: недели с понедельника, крайние захватывают соседние кварталы', () => {
    const weeks = quarterWeeks(2026, 4);
    expect(weeks).toHaveLength(14);
    expect(weeks[0].start).toBe('2026-09-28');
    expect(weeks[0].days.map((d) => d.inQuarter)).toEqual([false, false, false, true, true, true, true]);
    expect(weeks[0].month).toBe(10);
    const last = weeks[weeks.length - 1];
    expect(last.start).toBe('2026-12-28');
    expect(last.days[3]).toEqual({ iso: '2026-12-31', inQuarter: true });
    expect(last.days[4].inQuarter).toBe(false);
    expect(last.month).toBe(12);
  });

  it('все дни квартала попадают ровно один раз', () => {
    const days = quarterWeeks(2026, 1).flatMap((w) => w.days.filter((d) => d.inQuarter).map((d) => d.iso));
    expect(days).toHaveLength(90);
    expect(new Set(days).size).toBe(90);
    expect(days[0]).toBe('2026-01-01');
    expect(days[days.length - 1]).toBe('2026-03-31');
  });

  it('четверг вне квартала — неделя по первому дню квартала в ней', () => {
    // 1 апреля 2028 — суббота: четверг этой недели (30.03) ещё в первом квартале.
    const first = quarterWeeks(2028, 2)[0];
    expect(first.start).toBe('2028-03-27');
    expect(first.month).toBe(4);
  });

  it('подписи месяцев суммируются в число недель', () => {
    const weeks = quarterWeeks(2026, 4);
    const spans = weekMonthSpans(weeks);
    expect(spans.map((s) => s.month)).toEqual([10, 11, 12]);
    expect(spans.reduce((n, s) => n + s.span, 0)).toBe(weeks.length);
  });
});
