/** Подпись «Кому» заблокированного периода. */
export function blockAudience(b: { role_labels?: string[]; employee_names?: string[] }): string {
  const roles = (b.role_labels ?? []).join(', ');
  const people = (b.employee_names ?? []).join(', ');
  if (!roles && !people) return 'вся команда';
  return [roles, people].filter(Boolean).join(' · ');
}

/** Пометка «на кого не действует»: по месяцам, в порядке месяцев. Пусто — действует на всех. */
export function notAppliedText(b: {
  not_applied?: { employee_name: string; month: string }[];
}): string {
  const byMonth = new Map<string, string[]>();
  for (const x of b.not_applied ?? []) {
    byMonth.set(x.month, [...(byMonth.get(x.month) ?? []), x.employee_name]);
  }
  if (byMonth.size === 0) return '';
  const parts = [...byMonth.entries()]
    .sort(([a], [c]) => a.localeCompare(c))
    .map(([month, names]) => {
      const m = new Date(`${month}T00:00:00`).toLocaleString('ru-RU', { month: 'long' });
      return `в ${monthPrepositional(m)} — ${names.join(', ')}`;
    });
  return `Не действует ${parts.join('; ')}: у них свой период того же вида по роли или лично.`;
}

// «октябрь» → «октябре», «май» → «мае», «март» → «марте».
function monthPrepositional(m: string): string {
  if (m.endsWith('й') || m.endsWith('ь')) return `${m.slice(0, -1)}е`;
  return `${m}е`;
}
