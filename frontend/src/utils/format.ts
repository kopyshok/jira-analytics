export function formatHours(hours: number | null | undefined): string {
  if (hours == null) return '—';
  return hours.toFixed(1);
}

export function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatDateOnly(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

export function daysSince(iso: string | null, now: Date = new Date()): number | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  return Math.floor((now.getTime() - then) / (1000 * 60 * 60 * 24));
}

/** Human-readable "time ago" in Russian — «2 ч назад», «5 мин назад», «3 д назад». */
export function timeAgo(iso: string | null, now: Date = new Date()): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const diffS = Math.floor((now.getTime() - then) / 1000);
  if (diffS < 60) return 'только что';
  const diffM = Math.floor(diffS / 60);
  if (diffM < 60) return `${diffM} мин назад`;
  const diffH = Math.floor(diffM / 60);
  if (diffH < 24) return `${diffH} ч назад`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 30) return `${diffD} д назад`;
  const diffMo = Math.floor(diffD / 30);
  return `${diffMo} мес назад`;
}
