import type { ExternalBookingOut } from '../api/resourcePlanning';
import { PHASE_LABELS } from './gantt';

/** «OS-91393 · Разработка · Пряничников». */
export function externalBookingLabel(b: ExternalBookingOut): string {
  return [b.issue_key ?? b.title, PHASE_LABELS[b.phase] ?? b.phase, b.employee_name ?? '']
    .filter(Boolean)
    .join(' · ');
}

export interface ExternalBookingGroup {
  employee_id: string;
  employee_name: string;
  rows: ExternalBookingOut[];
}

/** Брони по сотрудникам (по алфавиту), внутри — по дате начала. */
export function groupExternalBookings(bookings: ExternalBookingOut[]): ExternalBookingGroup[] {
  const map = new Map<string, ExternalBookingGroup>();
  for (const b of bookings) {
    let g = map.get(b.employee_id);
    if (!g) {
      g = { employee_id: b.employee_id, employee_name: b.employee_name ?? '', rows: [] };
      map.set(b.employee_id, g);
    }
    g.rows.push(b);
  }
  const out = [...map.values()];
  for (const g of out) g.rows.sort((x, y) => x.start.localeCompare(y.start));
  out.sort((x, y) => x.employee_name.localeCompare(y.employee_name, 'ru'));
  return out;
}

export interface BookingRun {
  start: string;
  end: string;
  hours: number;
}

const isWeekday = (iso: string) => {
  const dow = new Date(iso + 'T00:00:00').getDay();
  return dow !== 0 && dow !== 6;
};

/** Следующий календарный день: «2026-01-09» → «2026-01-10». */
function nextIso(iso: string): string {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

/**
 * Отрезки занятости брони внутри [from, to]: подряд идущие дни с часами.
 * Нерабочие дни между ними отрезок не рвут — окно видно только там, где
 * человек в рабочий день свободен (планировщик оставляет паузы внутри фазы).
 */
export function bookingRuns(
  daily: Record<string, number>,
  from: string,
  to: string,
  isWorkday: (iso: string) => boolean = isWeekday,
): BookingRun[] {
  const days = Object.keys(daily)
    .filter((d) => daily[d] > 0 && d >= from && d <= to)
    .sort();
  const runs: BookingRun[] = [];
  for (const d of days) {
    const last = runs[runs.length - 1];
    if (last) {
      let gapIsOff = true;
      for (let g = nextIso(last.end); g < d; g = nextIso(g)) {
        if (isWorkday(g)) {
          gapIsOff = false;
          break;
        }
      }
      if (gapIsOff) {
        last.end = d;
        last.hours += daily[d];
        continue;
      }
    }
    runs.push({ start: d, end: d, hours: daily[d] });
  }
  return runs;
}
