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
