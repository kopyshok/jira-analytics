import type { AssignmentOut, ExternalBookingOut } from '../api/resourcePlanning';
import { nextIso } from './externalBookings';
import { PHASE_LABELS } from './gantt';

/** Вырез в полосе фазы: рабочий день без её часов, когда человек занят в другой команде. */
export interface BusyGap {
  date: string;
  /** «занят в плане ERP ТУ · OS-7 Разработка», по строке на бронь. */
  label: string;
}

const phaseName = (phase: string) => PHASE_LABELS[phase] ?? phase;
const bookingName = (b: ExternalBookingOut) => `${b.issue_key ?? b.title} ${phaseName(b.phase)}`;
const fmtHours = (h: number) => (Math.round(h * 10) / 10).toLocaleString('ru');

/**
 * Рабочие дни внутри полосы, где у фазы нет часов, а человек занят в плане
 * другой команды. Фаза без посуточной раскладки вырезов не получает.
 */
export function busyGaps(
  a: AssignmentOut,
  bookings: ExternalBookingOut[],
  isWorkday: (iso: string) => boolean,
): BusyGap[] {
  const { employee_id: employeeId, start_date: start, end_date: end, daily_hours: daily } = a;
  if (!employeeId || !start || !end || !daily) return [];
  const mine = bookings.filter((b) => b.employee_id === employeeId);
  if (mine.length === 0) return [];
  const out: BusyGap[] = [];
  for (let d = start; d <= end; d = nextIso(d)) {
    if (!isWorkday(d) || (daily[d] ?? 0) > 0) continue;
    const busy = mine.filter((b) => (b.daily_hours[d] ?? 0) > 0);
    if (busy.length === 0) continue;
    out.push({
      date: d,
      label: busy.map((b) => `занят в плане ${b.team} · ${bookingName(b)}`).join('\n'),
    });
  }
  return out;
}

/**
 * Строки подсказки дня в подвале: «этот план N ч: KEY Фаза; …» и по строке
 * на каждую другую команду «<команда> N ч: KEY Фаза; …». Пусто — дня нет.
 */
export function dayTooltipLines(
  employeeId: string,
  date: string,
  assignments: AssignmentOut[],
  bookings: ExternalBookingOut[],
): string[] {
  const lines: string[] = [];
  const own = assignments.filter(
    (a) => a.employee_id === employeeId && (a.daily_hours?.[date] ?? 0) > 0,
  );
  if (own.length > 0) {
    const total = own.reduce((s, a) => s + (a.daily_hours?.[date] ?? 0), 0);
    const names = own.map((a) => `${a.backlog_item_key ?? a.backlog_item_title} ${phaseName(a.phase)}`);
    lines.push(`этот план ${fmtHours(total)} ч: ${names.join('; ')}`);
  }
  const byTeam = new Map<string, ExternalBookingOut[]>();
  for (const b of bookings) {
    if (b.employee_id !== employeeId || (b.daily_hours[date] ?? 0) <= 0) continue;
    byTeam.set(b.team, [...(byTeam.get(b.team) ?? []), b]);
  }
  for (const team of [...byTeam.keys()].sort((x, y) => x.localeCompare(y, 'ru'))) {
    const list = byTeam.get(team) ?? [];
    const total = list.reduce((s, b) => s + (b.daily_hours[date] ?? 0), 0);
    lines.push(`${team} ${fmtHours(total)} ч: ${list.map(bookingName).join('; ')}`);
  }
  return lines;
}
