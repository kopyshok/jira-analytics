import { describe, it, expect } from 'vitest';
import { filterByPeople, peopleSections, personLaneRuns } from './rpPeople';
import { workdayChecker } from './externalBookings';
import type { AssignmentOut, EmployeeLoadOut, ExternalBookingOut } from '../api/resourcePlanning';

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
  end_date: '2026-01-08',
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
  employee_is_borrowed: false,
  is_borrowing: true,
  overlap_days: [],
  ...over,
});

const load = (over: Partial<EmployeeLoadOut> = {}): EmployeeLoadOut => ({
  employee_id: 'e1',
  employee_name: 'Шутов',
  employee_role: 'developer',
  days: [
    { date: '2026-01-05', pct: 100 },
    { date: '2026-01-06', pct: 50 },
    { date: '2026-01-10', pct: 0, off: 'weekend' },
  ],
  ...over,
});

describe('peopleSections', () => {
  it('свои по имени, затем привлечённые, в конце «Без исполнителя»', () => {
    const sections = peopleSections(
      [
        a({ id: 'q', employee_id: null, employee_name: null, phase: 'qa' }),
        a({ id: 'x', employee_id: 'e3', employee_name: 'Андреев' }),
        a({ id: 'y', employee_id: 'e2', employee_name: 'Яковлев' }),
        a({ id: 'z' }),
      ],
      [],
      [
        load({ employee_id: 'e3', employee_name: 'Андреев', is_borrowed: true, borrowed_from: 'ERP ТУ' }),
        load({ employee_id: 'e2', employee_name: 'Яковлев' }),
        load(),
      ],
      'СФО',
    );
    expect(sections.map((s) => s.name)).toEqual(['Шутов', 'Яковлев', 'Андреев', 'Без исполнителя']);
    expect(sections.map((s) => s.teamNote)).toEqual(['СФО', 'СФО', 'из ERP ТУ', '']);
    expect(sections[2].isBorrowed).toBe(true);
  });
  it('части одной фазы — одна строка; строки по дате начала', () => {
    const [s] = peopleSections(
      [
        a({ id: 'p2', part_number: 2, start_date: '2026-01-20', hours_allocated: 4 }),
        a({ id: 'an', backlog_item_id: 'i2', backlog_item_key: 'OS-2', phase: 'analyst', start_date: '2026-01-02' }),
        a({ id: 'p1', start_date: '2026-01-05', hours_allocated: 8 }),
      ],
      [],
      [load()],
      'СФО',
    );
    expect(s.rows.map((r) => r.key)).toEqual(['i2-analyst', 'i1-dev']);
    expect(s.rows[1].assignments.map((x) => x.id)).toEqual(['p1', 'p2']);
    expect(s.rows[1].hours).toBe(12);
  });
  it('загрузка — средняя по рабочим дням; брони — только свои', () => {
    const [s] = peopleSections([a()], [b(), b({ assignment_id: 'x2', employee_id: 'e2' })], [load()], 'СФО');
    expect(s.loadPct).toBe(75);
    expect(s.bookings.map((x) => x.assignment_id)).toEqual(['x1']);
  });
});

describe('personLaneRuns', () => {
  it('фазы этого плана и брони других команд — по дате', () => {
    const [s] = peopleSections([a()], [b()], [load()], 'СФО');
    expect(personLaneRuns(s, '2026-01-01', '2026-03-31', weekdays)).toEqual([
      { kind: 'phase', phase: 'dev', start: '2026-01-05', end: '2026-01-05', hours: 6, label: 'OS-1 · Разработка' },
      { kind: 'booking', start: '2026-01-06', end: '2026-01-07', hours: 12, label: 'OS-7 · Разработка — ERP ТУ' },
      { kind: 'phase', phase: 'dev', start: '2026-01-08', end: '2026-01-08', hours: 6, label: 'OS-1 · Разработка' },
    ]);
  });
});

describe('filterByPeople', () => {
  it('пустой выбор — все строки; иначе только выбранные люди, без строк без человека', () => {
    const rows = [a(), a({ id: 'a2', employee_id: 'e2' }), a({ id: 'q', employee_id: null })];
    expect(filterByPeople(rows, [])).toBe(rows);
    expect(filterByPeople(rows, ['e2']).map((r) => r.id)).toEqual(['a2']);
  });
});
