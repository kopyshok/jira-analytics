import { describe, it, expect } from 'vitest';
import {
  bookingRuns, externalBookingLabel, groupExternalBookings, ownPeopleBookingLabel,
  phaseCountLabel, workdayChecker,
} from './externalBookings';
import type { ExternalBookingOut } from '../api/resourcePlanning';

const b = (over: Partial<ExternalBookingOut>): ExternalBookingOut => ({
  assignment_id: 'a1',
  employee_id: 'e1',
  employee_name: 'Пряничников',
  team: 'Команда 1С',
  issue_key: 'OS-91393',
  title: 'Задача',
  phase: 'dev',
  start: '2026-01-05',
  end: '2026-01-06',
  daily_hours: {},
  provisional: false,
  employee_is_borrowed: true,
  is_borrowing: false,
  overlap_days: [],
  ...over,
});

describe('externalBookingLabel', () => {
  it('ключ · фаза · фамилия', () => {
    expect(externalBookingLabel(b({}))).toBe('OS-91393 · Разработка · Пряничников');
  });
  it('без ключа — название задачи', () => {
    expect(externalBookingLabel(b({ issue_key: null, phase: 'analyst' }))).toBe(
      'Задача · Анализ · Пряничников',
    );
  });
});

describe('phaseCountLabel', () => {
  it('склоняет «фаза» по числу', () => {
    expect([1, 2, 4, 5, 11, 12, 14, 21, 22, 25, 111].map(phaseCountLabel)).toEqual([
      '1 фаза', '2 фазы', '4 фазы', '5 фаз', '11 фаз', '12 фаз', '14 фаз',
      '21 фаза', '22 фазы', '25 фаз', '111 фаз',
    ]);
  });
});

describe('groupExternalBookings', () => {
  it('по сотруднику, внутри — по дате начала, сотрудники по алфавиту', () => {
    const groups = groupExternalBookings([
      b({ assignment_id: 'x2', start: '2026-02-01' }),
      b({ assignment_id: 'y1', employee_id: 'e2', employee_name: 'Андреев' }),
      b({ assignment_id: 'x1', start: '2026-01-10' }),
    ]);
    expect(groups.map(g => g.employee_id)).toEqual(['e2', 'e1']);
    expect(groups[1].rows.map(r => r.assignment_id)).toEqual(['x1', 'x2']);
  });
});

describe('bookingRuns', () => {
  // 2026-01-09 — пятница, 01-12 — понедельник, 01-13 — вторник, 01-14 — среда.
  it('выходные между днями с часами отрезок не рвут', () => {
    expect(
      bookingRuns({ '2026-01-09': 4, '2026-01-12': 3 }, '2026-01-01', '2026-03-31'),
    ).toEqual([{ start: '2026-01-09', end: '2026-01-12', hours: 7 }]);
  });
  it('свободный рабочий день — окно между отрезками', () => {
    expect(
      bookingRuns({ '2026-01-12': 4, '2026-01-14': 4 }, '2026-01-01', '2026-03-31'),
    ).toEqual([
      { start: '2026-01-12', end: '2026-01-12', hours: 4 },
      { start: '2026-01-14', end: '2026-01-14', hours: 4 },
    ]);
  });
  it('праздник по календарю не считается окном', () => {
    const isWorkday = (iso: string) => iso !== '2026-01-13';
    expect(
      bookingRuns({ '2026-01-12': 4, '2026-01-14': 4 }, '2026-01-01', '2026-03-31', isWorkday),
    ).toEqual([{ start: '2026-01-12', end: '2026-01-14', hours: 8 }]);
  });
  it('дни вне окна диаграммы и нулевые часы отбрасываются', () => {
    expect(
      bookingRuns(
        { '2025-12-31': 6, '2026-01-12': 0, '2026-01-13': 2, '2026-04-01': 6 },
        '2026-01-01',
        '2026-03-31',
      ),
    ).toEqual([{ start: '2026-01-13', end: '2026-01-13', hours: 2 }]);
  });
});

describe('ownPeopleBookingLabel', () => {
  it('имя · ключ · фаза', () => {
    expect(ownPeopleBookingLabel(b({}))).toBe('Пряничников · OS-91393 · Разработка');
  });
});

describe('workdayChecker', () => {
  it('производственный календарь важнее дня недели', () => {
    const isWorkday = workdayChecker([
      { date: '2026-01-05', is_workday: false },
      { date: '2026-01-10', is_workday: true },
    ]);
    expect(isWorkday('2026-01-05')).toBe(false); // праздник в понедельник
    expect(isWorkday('2026-01-10')).toBe(true); // рабочая суббота
    expect(isWorkday('2026-01-06')).toBe(true);
    expect(isWorkday('2026-01-11')).toBe(false);
  });
});
