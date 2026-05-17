import { describe, it, expect } from 'vitest';
import { buildWorkdayTimeline, dateToLeft, datesToWidth } from './gantt';

describe('buildWorkdayTimeline', () => {
  it('skips weekends without production calendar', () => {
    const start = new Date(2026, 3, 1); // Wed Apr 1
    const end = new Date(2026, 3, 10);  // Fri Apr 10
    const tl = buildWorkdayTimeline(start, end, []);
    // Apr 1 (Wed), 2 (Thu), 3 (Fri) + Apr 6 (Mon), 7, 8, 9, 10 = 8 workdays
    expect(tl.totalDays).toBe(8);
    expect(tl.workdayDates).toContain('2026-04-06');
    expect(tl.workdayDates).not.toContain('2026-04-04'); // Sat
    expect(tl.workdayDates).not.toContain('2026-04-05'); // Sun
  });

  it('respects production calendar holidays', () => {
    const start = new Date(2026, 4, 1);
    const end = new Date(2026, 4, 12);
    const calendar = [{ date: '2026-05-01', hours: 0, is_workday: false, kind: 'holiday' }];
    const tl = buildWorkdayTimeline(start, end, calendar);
    expect(tl.workdayDates).not.toContain('2026-05-01');
  });

  it('dateToLeft uses workday index in workday mode', () => {
    const start = new Date(2026, 3, 1);
    const end = new Date(2026, 3, 10);
    const tl = buildWorkdayTimeline(start, end, []);
    // Apr 1 (idx 0), Apr 2 (idx 1), Apr 3 (idx 2), Apr 6 (idx 3)
    expect(dateToLeft('2026-04-06', tl)).toBeCloseTo(3 / 8 * 100, 1);
  });

  it('datesToWidth counts workdays in range', () => {
    const start = new Date(2026, 3, 1);
    const end = new Date(2026, 3, 10);
    const tl = buildWorkdayTimeline(start, end, []);
    // Apr 3 (Fri) to Apr 8 (Wed): Apr 3, Apr 6, Apr 7, Apr 8 = 4 workdays out of 8
    expect(datesToWidth('2026-04-03', '2026-04-08', tl)).toBeCloseTo(4 / 8 * 100, 1);
  });

  it('dateToLeft snaps non-working day to next workday', () => {
    const start = new Date(2026, 3, 1);
    const end = new Date(2026, 3, 10);
    const tl = buildWorkdayTimeline(start, end, []);
    // Apr 4 (Sat) → snaps to Apr 6 (Mon, idx 3)
    expect(dateToLeft('2026-04-04', tl)).toBeCloseTo(3 / 8 * 100, 1);
  });

  it('datesToWidth returns 0.5 minimum for all-weekend range', () => {
    const start = new Date(2026, 3, 1);
    const end = new Date(2026, 3, 10);
    const tl = buildWorkdayTimeline(start, end, []);
    // Apr 4 (Sat) to Apr 5 (Sun) = 0 workdays → minimum 0.5
    expect(datesToWidth('2026-04-04', '2026-04-05', tl)).toBe(0.5);
  });
});
