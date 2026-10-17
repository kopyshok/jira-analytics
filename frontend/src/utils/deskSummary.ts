import type { DeskDeveloper, DeskIssue } from '../api/teamDesk';

/**
 * Точность оценок по всему срезу — тем же правилом, что у плитки человека на
 * сервере: медиана «факт / оценка» по самостоятельным задачам, у которых есть
 * и оценка, и списания.
 */
export function teamAccuracy(issues: DeskIssue[]): number | null {
  const ratios = issues
    .filter((i) => i.is_standalone && i.est_hours && i.fact_hours > 0)
    .map((i) => i.fact_hours / (i.est_hours as number))
    .sort((a, b) => a - b);
  if (!ratios.length) return null;
  const mid = Math.floor(ratios.length / 2);
  const median = ratios.length % 2 ? ratios[mid] : (ratios[mid - 1] + ratios[mid]) / 2;
  return Math.round(median * 100) / 100;
}

/** Сколько задач в срезе: сумма по людям — задачи разбиты по владельцам без задвоений. */
export function deskTaskCount(developers: DeskDeveloper[]): number {
  return developers.reduce((n, d) => n + d.total_issues, 0);
}

/** «разработчик / разработчика / разработчиков». */
export function developersWord(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return 'разработчик';
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'разработчика';
  return 'разработчиков';
}

/** «задача / задачи / задач». */
export function tasksWord(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return 'задача';
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'задачи';
  return 'задач';
}
