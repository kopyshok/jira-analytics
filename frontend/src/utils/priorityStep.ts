export const PRIORITY_MIN = 1;
export const PRIORITY_MAX = 10;

/** Кнопки ▲ (+1) и ▼ (−1) у приоритета: в пределах 1..10, пустой ▲ ставит 1, ▼ ничего не делает. */
export function stepPriority(current: number | null, dir: 1 | -1): number | null {
  if (current == null) return dir === 1 ? PRIORITY_MIN : null;
  return Math.min(PRIORITY_MAX, Math.max(PRIORITY_MIN, current + dir));
}

export function canStepPriority(current: number | null, dir: 1 | -1): boolean {
  if (current == null) return dir === 1;
  return dir === 1 ? current < PRIORITY_MAX : current > PRIORITY_MIN;
}
