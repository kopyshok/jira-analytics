import { describe, expect, it } from 'vitest';
import dayjs from 'dayjs';
import { absenceInWeek, quarterWeeks } from './absenceWeeksMath';
import type { AbsenceResponse } from '../../types/api';

const absence = (start: string, end: string): AbsenceResponse =>
  ({ employee_id: 'e1', start_date: start, end_date: end, reason_label: 'Отпуск', reason_color: '#F0A04B' }) as AbsenceResponse;

describe('quarterWeeks', () => {
  it('Q4 2026: недели с понедельника, первая задевает 1 октября', () => {
    const { qStart, qEnd, weeks } = quarterWeeks(2026, 4);
    expect(qStart.format('YYYY-MM-DD')).toBe('2026-10-01');
    expect(qEnd.format('YYYY-MM-DD')).toBe('2026-12-31');
    expect(weeks[0].format('YYYY-MM-DD')).toBe('2026-09-28');
    expect(weeks.every((w) => w.day() === 1)).toBe(true);
    expect(weeks[weeks.length - 1].isAfter(qEnd)).toBe(false);
    expect(weeks).toHaveLength(14);
  });
});

describe('absenceInWeek', () => {
  const { qStart, qEnd } = quarterWeeks(2026, 4);
  it('находит отпуск, задевающий рабочие дни недели', () => {
    const list = [absence('2026-10-07', '2026-10-09')];
    expect(absenceInWeek(list, dayjs('2026-10-05'), qStart, qEnd)).not.toBeNull();
    expect(absenceInWeek(list, dayjs('2026-10-12'), qStart, qEnd)).toBeNull();
  });
  it('выходные недели не считаются, дни до квартала — тоже', () => {
    expect(absenceInWeek([absence('2026-10-10', '2026-10-11')], dayjs('2026-10-05'), qStart, qEnd)).toBeNull();
    expect(absenceInWeek([absence('2026-09-28', '2026-09-30')], dayjs('2026-09-28'), qStart, qEnd)).toBeNull();
  });
});
