import type { MultiTeamProgress, MultiTeamTeamTake, TeamTakeStatus } from '../types/api';

/** Цвет плашки «в работе у K из N»:
 *  none — никто не взял (серый), done — взяли все (зелёный),
 *  alert — часть взяла, а команда строки ещё нет (яркий), neutral — часть взяла,
 *  и команда строки среди взявших (или не участник). */
export type ProgressTone = 'none' | 'alert' | 'neutral' | 'done';

export function progressTone(p: MultiTeamProgress): ProgressTone {
  if (p.taken === 0) return 'none';
  if (p.taken >= p.total) return 'done';
  if (p.own_status === 'not_taken' || p.own_status === 'no_epic') return 'alert';
  return 'neutral';
}

/** Работу по RFA уже взяла другая команда — не команда строки. */
export function neighborsTaken(p: MultiTeamProgress | null | undefined): boolean {
  return !!p && p.teams.some((t) => t.status === 'taken' && t.team !== p.own_team);
}

const STATUS_LABEL: Record<TeamTakeStatus, string> = {
  taken: 'взят в работу',
  not_taken: 'эпик есть, не взят',
  no_epic: 'нет эпика',
};

/** Строка подсказки по одной команде. */
export function teamTakeLine(t: MultiTeamTeamTake): string {
  const head = `${t.team} — ${STATUS_LABEL[t.status]}`;
  if (!t.scenarios.length) return head;
  return `${head}: ${t.scenarios.map((s) => `«${s.name}», ${s.quarter_label}`).join('; ')}`;
}

const isOne = (n: number) => n % 10 === 1 && n % 100 !== 11;
const isFew = (n: number) => [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100);

/** «N задач уже взяли соседи, у вас не включены» — с согласованием числа. */
export function neighborsTakenTitle(n: number): string {
  const word = isOne(n) ? 'задачу' : isFew(n) ? 'задачи' : 'задач';
  return `${n} ${word} уже взяли соседи, у вас ${isOne(n) ? 'не включена' : 'не включены'}`;
}
