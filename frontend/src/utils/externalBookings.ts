import type { ExternalBookingOut } from '../api/resourcePlanning';
import { PHASE_LABELS } from './gantt';

/** «OS-91393 · Разработка · Пряничников». */
export function externalBookingLabel(b: ExternalBookingOut): string {
  return [b.issue_key ?? b.title, PHASE_LABELS[b.phase] ?? b.phase, b.employee_name ?? '']
    .filter(Boolean)
    .join(' · ');
}

/** «Шутов · OS-91393 · Разработка» — строка блока «Наши люди в других командах». */
export function ownPeopleBookingLabel(b: ExternalBookingOut): string {
  return [b.employee_name ?? '', b.issue_key ?? b.title, PHASE_LABELS[b.phase] ?? b.phase]
    .filter(Boolean)
    .join(' · ');
}

/** Серая штриховка чужой работы — только просмотр. */
export const OTHER_TEAM_HATCH =
  'repeating-linear-gradient(45deg, rgba(160,170,190,0.55) 0 4px, rgba(160,170,190,0.18) 4px 8px)';

/** «1 фаза», «3 фазы», «12 фаз» — счётчик в шапке блока «Привлечённые». */
export function phaseCountLabel(n: number): string {
  const d = n % 10;
  const dd = n % 100;
  if (d === 1 && dd !== 11) return `${n} фаза`;
  if (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) return `${n} фазы`;
  return `${n} фаз`;
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

/** Рабочий ли день: производственный календарь, иначе Пн–Пт. */
export function workdayChecker(
  calendar: ReadonlyArray<{ date: string; is_workday: boolean }>,
): (iso: string) => boolean {
  const known = new Map(calendar.map((c) => [c.date, c.is_workday] as const));
  return (iso) => known.get(iso) ?? isWeekday(iso);
}

/** Следующий календарный день: «2026-01-09» → «2026-01-10». */
export function nextIso(iso: string): string {
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
