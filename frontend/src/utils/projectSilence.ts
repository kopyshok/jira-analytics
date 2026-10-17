/**
 * Подпись «тишины» проекта на дашборде. `silentDays` — дни с последнего
 * списания; null — по проекту часов не списывали ни разу.
 * Пусто — проект не молчит, подпись не нужна.
 */
export function silenceLabel(silentDays: number | null, threshold: number): string | null {
  if (silentDays == null) return 'списаний не было';
  return silentDays > threshold ? `тишина ${silentDays}д` : null;
}
