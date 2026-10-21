import dayjs from 'dayjs';
import type { AbsenceResponse } from '../../types/api';

/** Границы квартала и понедельники недель, которые его задевают. */
export function quarterWeeks(year: number, quarter: number) {
  const qStart = dayjs(`${year}-${String((quarter - 1) * 3 + 1).padStart(2, '0')}-01`);
  const qEnd = qStart.add(3, 'month').subtract(1, 'day');
  const firstMonday = qStart.subtract((qStart.day() + 6) % 7, 'day');
  const weeks: dayjs.Dayjs[] = [];
  for (let w = firstMonday; !w.isAfter(qEnd); w = w.add(7, 'day')) weeks.push(w);
  return { qStart, qEnd, weeks };
}

/** Отсутствие, задевающее рабочие дни (пн–пт) недели внутри квартала. */
export function absenceInWeek(
  list: AbsenceResponse[] | undefined, monday: dayjs.Dayjs, qStart: dayjs.Dayjs, qEnd: dayjs.Dayjs,
): AbsenceResponse | null {
  if (!list) return null;
  const from = monday.isBefore(qStart) ? qStart : monday;
  const friday = monday.add(4, 'day');
  const to = friday.isAfter(qEnd) ? qEnd : friday;
  for (const a of list) {
    if (dayjs(a.end_date).isBefore(from, 'day') || dayjs(a.start_date).isAfter(to, 'day')) continue;
    return a;
  }
  return null;
}
