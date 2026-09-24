import type { AssignmentOut, EmployeeLoadOut, ExternalBookingOut } from '../api/resourcePlanning';
import { bookingRuns, type BookingRun } from './externalBookings';
import { PHASE_LABELS } from './gantt';

/** Строка фазы в секции человека: все части одной фазы одной задачи. */
export interface PersonRow {
  key: string;
  itemId: string;
  itemKey: string | null;
  itemTitle: string;
  phase: AssignmentOut['phase'];
  hours: number;
  assignments: AssignmentOut[];
}

/** Секция вида «Исполнители». employeeId = null — фазы без человека. */
export interface PersonSection {
  employeeId: string | null;
  name: string;
  role: string | null;
  /** Подпись: команда плана или «из <команда>» у привлечённого. */
  teamNote: string;
  isBorrowed: boolean;
  /** Средняя загрузка в этом плане по рабочим дням квартала, %; null — нет строки подвала. */
  loadPct: number | null;
  rows: PersonRow[];
  bookings: ExternalBookingOut[];
}

/** Отрезок полосы «все работы»: фаза этого плана или бронь другой команды. */
export type LaneRun = BookingRun & { label: string } & (
  | { kind: 'phase'; phase: AssignmentOut['phase'] }
  | { kind: 'booking' }
);

/** Средняя загрузка по рабочим дням — как бейдж подвала. */
function avgLoad(row: EmployeeLoadOut): number {
  const work = row.days.filter((d) => !d.off);
  return work.length ? Math.round(work.reduce((s, d) => s + d.pct, 0) / work.length) : 0;
}

/**
 * Секции вида «Исполнители»: каждый, у кого есть фазы в плане. Сначала свои
 * (по имени), затем привлечённые, в конце — «Без исполнителя».
 */
export function peopleSections(
  assignments: AssignmentOut[],
  bookings: ExternalBookingOut[],
  loadRows: EmployeeLoadOut[],
  planTeam: string | null,
): PersonSection[] {
  const loadBy = new Map(loadRows.map((r) => [r.employee_id, r] as const));
  const byPerson = new Map<string | null, AssignmentOut[]>();
  for (const a of assignments) {
    byPerson.set(a.employee_id, [...(byPerson.get(a.employee_id) ?? []), a]);
  }
  const sections: PersonSection[] = [];
  for (const [employeeId, list] of byPerson) {
    const rowsByKey = new Map<string, PersonRow>();
    for (const a of list) {
      const key = `${a.backlog_item_id}-${a.phase}`;
      const row = rowsByKey.get(key) ?? {
        key,
        itemId: a.backlog_item_id,
        itemKey: a.backlog_item_key,
        itemTitle: a.backlog_item_title,
        phase: a.phase,
        hours: 0,
        assignments: [],
      };
      row.hours += a.hours_allocated ?? 0;
      row.assignments.push(a);
      rowsByKey.set(key, row);
    }
    const firstStart = (r: PersonRow) =>
      r.assignments.map((x) => x.start_date ?? '9999-12-31').sort()[0];
    const rows = [...rowsByKey.values()].sort(
      (x, y) => firstStart(x).localeCompare(firstStart(y)) || x.key.localeCompare(y.key),
    );
    for (const r of rows) r.assignments.sort((x, y) => x.part_number - y.part_number);
    const load = employeeId ? loadBy.get(employeeId) : undefined;
    const isBorrowed = !!load?.is_borrowed;
    sections.push({
      employeeId,
      name: employeeId ? (load?.employee_name ?? list[0].employee_name ?? '—') : 'Без исполнителя',
      role: load?.employee_role ?? list[0].employee_role ?? null,
      teamNote: !employeeId ? '' : isBorrowed ? `из ${load?.borrowed_from ?? 'другой команды'}` : (planTeam ?? ''),
      isBorrowed,
      loadPct: load ? avgLoad(load) : null,
      rows,
      bookings: employeeId ? bookings.filter((b) => b.employee_id === employeeId) : [],
    });
  }
  const rank = (s: PersonSection) => (s.employeeId === null ? 2 : s.isBorrowed ? 1 : 0);
  return sections.sort((x, y) => rank(x) - rank(y) || x.name.localeCompare(y.name, 'ru'));
}

/**
 * Полоса «все работы» человека: фазы этого плана (по дням с часами) и брони
 * других команд. Свободные дни остаются пустыми.
 */
export function personLaneRuns(
  section: PersonSection,
  from: string,
  to: string,
  isWorkday: (iso: string) => boolean,
): LaneRun[] {
  const out: LaneRun[] = [];
  for (const row of section.rows) {
    const label = `${row.itemKey ?? row.itemTitle} · ${PHASE_LABELS[row.phase] ?? row.phase}`;
    for (const a of row.assignments) {
      if (a.daily_hours) {
        for (const r of bookingRuns(a.daily_hours, from, to, isWorkday)) {
          out.push({ kind: 'phase', phase: a.phase, ...r, label });
        }
      } else if (a.start_date && a.end_date) {
        out.push({
          kind: 'phase', phase: a.phase, start: a.start_date, end: a.end_date,
          hours: a.hours_allocated ?? 0, label,
        });
      }
    }
  }
  for (const b of section.bookings) {
    const label = `${b.issue_key ?? b.title} · ${PHASE_LABELS[b.phase] ?? b.phase} — ${b.team}`;
    for (const r of bookingRuns(b.daily_hours, from, to, isWorkday)) {
      out.push({ kind: 'booking', ...r, label });
    }
  }
  return out.sort((x, y) => x.start.localeCompare(y.start) || x.kind.localeCompare(y.kind));
}

/** Только строки выбранных людей; пустой выбор — все строки как есть. */
export function filterByPeople<T extends { employee_id: string | null }>(
  rows: T[],
  people: readonly string[],
): T[] {
  if (people.length === 0) return rows;
  const wanted = new Set(people);
  return rows.filter((r) => r.employee_id !== null && wanted.has(r.employee_id));
}
