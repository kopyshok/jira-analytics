/**
 * Недели квартала для мини-карты отсутствий: неделя с понедельника, крайние
 * недели захватывают дни соседних кварталов (они помечены «вне квартала»).
 * Неделя относится к месяцу своего четверга, а если четверг вне квартала —
 * к месяцу первого дня квартала в ней.
 */

export interface QuarterDay {
  /** Дата YYYY-MM-DD. */
  iso: string;
  inQuarter: boolean;
}

export interface QuarterWeek {
  /** Понедельник недели, YYYY-MM-DD. */
  start: string;
  /** Месяц недели (1–12). */
  month: number;
  days: QuarterDay[];
}

const pad = (n: number) => String(n).padStart(2, '0');
const isoOf = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

export function quarterWeeks(year: number, quarter: number): QuarterWeek[] {
  const firstMonth = (quarter - 1) * 3;
  const first = new Date(year, firstMonth, 1);
  const last = new Date(year, firstMonth + 3, 0);
  // Понедельник недели, в которую попадает первый день квартала.
  const cursor = new Date(first);
  cursor.setDate(cursor.getDate() - ((cursor.getDay() + 6) % 7));
  const weeks: QuarterWeek[] = [];
  while (cursor <= last) {
    const days: QuarterDay[] = [];
    let month = 0;
    for (let i = 0; i < 7; i++) {
      const inQuarter = cursor >= first && cursor <= last;
      days.push({ iso: isoOf(cursor), inQuarter });
      if (i === 3 && inQuarter) month = cursor.getMonth() + 1;
      cursor.setDate(cursor.getDate() + 1);
    }
    if (!month) {
      const firstIn = days.find((d) => d.inQuarter)!;
      month = Number(firstIn.iso.slice(5, 7));
    }
    weeks.push({ start: days[0].iso, month, days });
  }
  return weeks;
}

/** Подписи месяцев над неделями: месяц и сколько недель под ним. */
export function weekMonthSpans(weeks: QuarterWeek[]): { month: number; span: number }[] {
  const spans: { month: number; span: number }[] = [];
  for (const week of weeks) {
    const tail = spans[spans.length - 1];
    if (tail && tail.month === week.month) tail.span += 1;
    else spans.push({ month: week.month, span: 1 });
  }
  return spans;
}
