import { describe, it, expect } from 'vitest';
import { busyGaps, dayTooltipLines } from './rpBusy';
import { workdayChecker } from './externalBookings';
import type { AssignmentOut, ExternalBookingOut } from '../api/resourcePlanning';

const weekdays = workdayChecker([]);

const a = (over: Partial<AssignmentOut> = {}): AssignmentOut => ({
  id: 'a1',
  backlog_item_id: 'i1',
  backlog_item_key: 'OS-1',
  backlog_item_title: 'Задача',
  phase: 'dev',
  employee_id: 'e1',
  employee_name: 'Шутов',
  employee_role: 'developer',
  part_number: 1,
  hours_allocated: 12,
  start_date: '2026-01-05',
  end_date: '2026-01-09',
  is_on_critical_path: false,
  slack_days: null,
  is_pinned: false,
  out_of_quarter: false,
  daily_hours: { '2026-01-05': 6, '2026-01-08': 6 },
  worklog_hours_actual: 0,
  ...over,
});

const b = (over: Partial<ExternalBookingOut> = {}): ExternalBookingOut => ({
  assignment_id: 'x1',
  employee_id: 'e1',
  employee_name: 'Шутов',
  team: 'ERP ТУ',
  issue_key: 'OS-7',
  title: 'Чужая',
  phase: 'dev',
  start: '2026-01-06',
  end: '2026-01-07',
  daily_hours: { '2026-01-06': 6, '2026-01-07': 6 },
  provisional: false,
  employee_is_borrowed: true,
  is_borrowing: false,
  overlap_days: [],
  ...over,
});

describe('busyGaps', () => {
  it('рабочий день внутри полосы без часов фазы, занятый другой командой, — вырез', () => {
    expect(busyGaps(a(), [b()], weekdays)).toEqual([
      { date: '2026-01-06', label: 'занят в плане ERP ТУ · OS-7 Разработка' },
      { date: '2026-01-07', label: 'занят в плане ERP ТУ · OS-7 Разработка' },
    ]);
  });
  it('день с часами фазы и день без брони — не вырезы', () => {
    expect(busyGaps(a(), [b({ daily_hours: { '2026-01-05': 2 } })], weekdays)).toEqual([]);
  });
  it('выходные и брони другого человека не в счёт', () => {
    const friToMon = a({
      start_date: '2026-01-09', end_date: '2026-01-12',
      daily_hours: { '2026-01-09': 6, '2026-01-12': 6 },
    });
    expect(busyGaps(friToMon, [b({ daily_hours: { '2026-01-10': 6, '2026-01-11': 6 } })], weekdays)).toEqual([]);
    expect(busyGaps(a(), [b({ employee_id: 'e2' })], weekdays)).toEqual([]);
  });
  it('фаза без посуточной раскладки — без вырезов', () => {
    expect(busyGaps(a({ daily_hours: null }), [b()], weekdays)).toEqual([]);
  });
  it('день отсутствия или блокировки — не вырез: их штриховка важнее', () => {
    const absent = a({ unavailable_days: [{ date: '2026-01-06', type: 'absence' }] });
    expect(busyGaps(absent, [b()], weekdays)).toEqual([
      { date: '2026-01-07', label: 'занят в плане ERP ТУ · OS-7 Разработка' },
    ]);
    const blocked = a({
      unavailable_days: [
        { date: '2026-01-06', type: 'block' },
        { date: '2026-01-07', type: 'block' },
      ],
    });
    expect(busyGaps(blocked, [b()], weekdays)).toEqual([]);
  });
  it('несколько броней в один день — по строке на каждую', () => {
    const second = b({
      assignment_id: 'x2', team: 'СФО', issue_key: 'OS-9', phase: 'analyst',
      daily_hours: { '2026-01-06': 2 },
    });
    expect(busyGaps(a(), [b(), second], weekdays)[0].label).toBe(
      'занят в плане ERP ТУ · OS-7 Разработка\nзанят в плане СФО · OS-9 Анализ',
    );
  });
});

describe('dayTooltipLines', () => {
  it('этот план и каждая другая команда — отдельной строкой', () => {
    const own = [
      a({ daily_hours: { '2026-01-06': 4 } }),
      a({ id: 'a2', backlog_item_key: 'OS-2', phase: 'analyst', daily_hours: { '2026-01-06': 1.5 } }),
      a({ id: 'a3', employee_id: 'e2', daily_hours: { '2026-01-06': 6 } }),
    ];
    const ext = [
      b({ team: 'СФО', daily_hours: { '2026-01-06': 2 } }),
      b({
        assignment_id: 'x2', team: 'Бухгалтерия', issue_key: null, title: 'Отчёт',
        phase: 'analyst', daily_hours: { '2026-01-06': 1 },
      }),
    ];
    expect(dayTooltipLines('e1', '2026-01-06', own, ext)).toEqual([
      'этот план 5,5 ч: OS-1 Разработка; OS-2 Анализ',
      'Бухгалтерия 1 ч: Отчёт Анализ',
      'СФО 2 ч: OS-7 Разработка',
    ]);
  });
  it('в этот день ничего — пустой список', () => {
    expect(dayTooltipLines('e1', '2026-01-10', [a()], [b()])).toEqual([]);
  });
});
