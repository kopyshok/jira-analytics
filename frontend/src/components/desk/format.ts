/** ISO-дата (YYYY-MM-DD) → DD.MM.YYYY. Пустое значение → прочерк. */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = iso.slice(0, 10).split('-');
  if (d.length !== 3) return iso;
  return `${d[2]}.${d[1]}.${d[0]}`;
}

/** Короткая дата DD.MM (без года). Пустое значение → прочерк. */
export function fmtShortDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = iso.slice(0, 10).split('-');
  if (d.length !== 3) return iso;
  return `${d[2]}.${d[1]}`;
}

/** Короткий диапазон дат DD.MM – DD.MM (одна строка). */
export function fmtShortRange(a: string | null | undefined, b: string | null | undefined): string {
  return `${fmtShortDate(a)} – ${fmtShortDate(b)}`;
}

const MONTH_GEN = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
];
const WEEKDAY_SHORT = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

/** Длинная русская дата: «16 июня 2026». */
export function fmtLongDate(d: Date): string {
  return `${d.getDate()} ${MONTH_GEN[d.getMonth()]} ${d.getFullYear()}`;
}

/** Короткая русская дата с днём недели: «13 июня, сб». */
export function fmtDayWithWeekday(iso: string): string {
  const d = new Date(iso.slice(0, 10));
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getDate()} ${MONTH_GEN[d.getMonth()]}, ${WEEKDAY_SHORT[d.getDay()]}`;
}

const ROMAN: Record<number, string> = { 1: 'I', 2: 'II', 3: 'III', 4: 'IV' };

/** Метка квартала: «II квартал 2026». */
export function fmtQuarter(year: number, quarter: number): string {
  return `${ROMAN[quarter] ?? quarter} квартал ${year}`;
}

/** Часы со знаком ±: «+14 ч» / «−8 ч» (минус — типографский). */
export function fmtSignedHours(h: number): string {
  const r = Math.round(h * 10) / 10;
  if (r > 0) return `+${r} ч`;
  if (r < 0) return `−${Math.abs(r)} ч`;
  return `0 ч`;
}

/** Инициалы из ФИО: «Иван Петров» → «ИП». */
export function initials(name: string | null | undefined): string {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

/** Относительная дата от сейчас: «сегодня», «вчера», «N дн. назад». */
export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return '—';
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return '—';
  const diffMs = Date.now() - then.getTime();
  const day = 86_400_000;
  const days = Math.floor(diffMs / day);
  if (days <= 0) return 'сегодня';
  if (days === 1) return 'вчера';
  if (days < 7) return `${days} дн. назад`;
  if (days < 30) {
    const w = Math.floor(days / 7);
    return `${w} нед. назад`;
  }
  if (days < 365) {
    const m = Math.floor(days / 30);
    return `${m} мес. назад`;
  }
  return fmtDate(iso);
}
