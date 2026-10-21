import type { DeskDeveloper, DeskIssue } from '../../api/teamDesk';

/** Уровень сигнала: перебор / недобор / в норме. */
export type SignalLevel = 'bad' | 'warn' | 'good';

/** Точность оценок разработчика: выше 1.3 — перебор, ниже 0.7 — недобор. */
export function accuracyLevel(value: number | null): SignalLevel | null {
  if (value == null) return null;
  if (value > 1.3) return 'bad';
  if (value < 0.7) return 'warn';
  return 'good';
}

/** Насколько плитка разработчика тревожная: 2 — перерасход, 1 — декомпозиция/зависла, 0 — спокойно. */
export function developerSeverity(dev: DeskDeveloper): 0 | 1 | 2 {
  if (dev.flag_counts.over) return 2;
  if (dev.flag_counts.decomp || dev.flag_counts.stale) return 1;
  return 0;
}

/** Остаток «резиновой» задачи: оценка минус факт; нет оценки — null. */
export function rubberLeft(row: DeskIssue): number | null {
  return row.est_hours == null ? null : Math.max(0, row.est_hours - row.fact_hours);
}

/** Сколько часов «резиновой» задачи уходит в очередь: норма за дни, но не больше остатка. */
export function rubberToQueue(row: DeskIssue, rubberDays: number): number {
  // Оценка — только потолок: нет её — вклад задаёт дневная норма.
  const byRate = (row.daily_rate ?? 0) * rubberDays;
  const value = rubberLeft(row);
  return value == null ? byRate : Math.min(byRate, value);
}
