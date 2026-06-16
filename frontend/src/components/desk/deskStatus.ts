/** Семантика статуса проекта на столе: по тексту статуса Jira → один из
 *  визуальных классов (точка / бейдж / полоса таймлайна). */
export type DeskStatusKind = 'active' | 'review' | 'done' | 'returned' | 'neutral';

export function deskStatusKind(status: string | null | undefined): DeskStatusKind {
  const s = (status ?? '').toLowerCase();
  if (!s) return 'neutral';
  if (s.includes('возвращ') || s.includes('return') || s.includes('reopen') || s.includes('отклон')) {
    return 'returned';
  }
  if (s.includes('ревью') || s.includes('review') || s.includes('провер') || s.includes('соглас')) {
    return 'review';
  }
  if (s.includes('готов') || s.includes('done') || s.includes('закры') || s.includes('заверш') || s.includes('выполн')) {
    return 'done';
  }
  if (s.includes('работе') || s.includes('progress') || s.includes('делаю') || s.includes('開')) {
    return 'active';
  }
  return 'neutral';
}

/** «В работе сейчас» — статус, по которому подсвечиваем активный проект. */
export function isInProgress(status: string | null | undefined): boolean {
  return deskStatusKind(status) === 'active';
}

export const STATUS_BADGE_LABEL: Record<DeskStatusKind, string> = {
  active: 'В работе',
  review: 'На ревью',
  done: 'Готово',
  returned: 'Возвращена',
  neutral: '',
};
