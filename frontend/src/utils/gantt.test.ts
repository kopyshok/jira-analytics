import { describe, it, expect } from 'vitest';
import {
  buildTimeline, buildWorkdayTimeline, dateToLeft, datesToWidth, findAssignmentByKey,
  shiftByColumns, startMovedNotice,
} from './gantt';

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

describe('shiftByColumns', () => {
  // Апрель 2026: 01.04 — среда, 03.04 — пятница, 04–05.04 — выходные.
  const days = buildTimeline(new Date(2026, 3, 1), new Date(2026, 3, 30));
  const workdays = buildWorkdayTimeline(new Date(2026, 3, 1), new Date(2026, 3, 30), []);

  it('в календарной шкале столбец — календарный день', () => {
    expect(shiftByColumns('2026-04-03', 3, days)).toBe('2026-04-06');
    expect(shiftByColumns('2026-04-06', -3, days)).toBe('2026-04-03');
  });

  it('в режиме «Только рабочие» столбец — рабочий день', () => {
    // Пт 03.04 + 3 столбца = Ср 08.04 (06, 07, 08), а не Пн 06.04.
    expect(shiftByColumns('2026-04-03', 3, workdays)).toBe('2026-04-08');
    expect(shiftByColumns('2026-04-08', -3, workdays)).toBe('2026-04-03');
  });

  it('нерабочий день считается от столбца следующего рабочего', () => {
    // Сб 04.04 стоит в столбце Пн 06.04.
    expect(shiftByColumns('2026-04-04', 1, workdays)).toBe('2026-04-07');
  });

  it('за краем шкалы — крайний рабочий день', () => {
    expect(shiftByColumns('2026-04-28', 10, workdays)).toBe('2026-04-30');
    expect(shiftByColumns('2026-04-02', -10, workdays)).toBe('2026-04-01');
    expect(shiftByColumns('2026-05-15', -1, workdays)).toBe('2026-04-30');
  });
});

describe('startMovedNotice', () => {
  it('сервер поставил начало на другой день — подсказка с датой', () => {
    expect(startMovedNotice('2026-10-05', '2026-10-12')).toBe(
      'Начало перенесено на первый свободный день: 12.10',
    );
  });

  it('начало там, куда просили, или его нет — без подсказки', () => {
    expect(startMovedNotice('2026-10-05', '2026-10-05')).toBeNull();
    expect(startMovedNotice('2026-10-05', null)).toBeNull();
  });
});

describe('findAssignmentByKey', () => {
  const key = { backlog_item_id: 'i1', phase: 'dev', part_number: 2 };

  it('finds the row with the same phase key after ids change', () => {
    const after = [
      { id: 'new-1', backlog_item_id: 'i1', phase: 'dev', part_number: 1 },
      { id: 'new-2', backlog_item_id: 'i1', phase: 'dev', part_number: 2 },
      { id: 'new-3', backlog_item_id: 'i2', phase: 'dev', part_number: 2 },
    ];
    expect(findAssignmentByKey(after, key)?.id).toBe('new-2');
  });

  it('returns null when the phase is gone (merged away) or no key', () => {
    expect(findAssignmentByKey([{ id: 'x', backlog_item_id: 'i1', phase: 'dev', part_number: 1 }], key)).toBeNull();
    expect(findAssignmentByKey([], null)).toBeNull();
  });
});
