const CURRENT_YEAR = new Date().getFullYear();

/** Годы для выбора в отборе проектов: прошлый, текущий и три вперёд. */
export function projectYearOptions(): { value: number; label: string }[] {
  return Array.from({ length: 5 }, (_, i) => {
    const y = CURRENT_YEAR - 1 + i;
    return { value: y, label: String(y) };
  });
}
