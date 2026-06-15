import { MONTH_NAMES } from '../../utils/constants';

/** ISO-дата (YYYY-MM-DD) → DD.MM.YYYY. Пустое значение → прочерк. */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = iso.slice(0, 10).split('-');
  if (d.length !== 3) return iso;
  return `${d[2]}.${d[1]}.${d[0]}`;
}

/** Диапазон дат DD.MM – DD.MM. */
export function fmtRange(a: string | null | undefined, b: string | null | undefined): string {
  return `${fmtDate(a)} – ${fmtDate(b)}`;
}

export function monthLabel(month: number): string {
  return MONTH_NAMES[month] ?? String(month);
}

export function fmtHours(h: number | null | undefined): string {
  if (h === null || h === undefined) return '—';
  return `${h} ч`;
}
