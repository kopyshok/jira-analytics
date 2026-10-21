/**
 * Форма слова после числа: `${n} ${plural(n, 'задача', 'задачи', 'задач')}` →
 * «1 задача», «3 задачи», «12 задач», «21 задача».
 *
 * one — для 1, 21, 101…; few — для 2–4, 22–24…; many — для 0, 5–20, 25–30….
 * Падеж задаёт вызывающий: «для 1 задачи / 2 задач» — plural(n, 'задачи', 'задач', 'задач').
 * Дробное число берёт форму few: «1,5 дня».
 */
export function plural(n: number, one: string, few: string, many: string): string {
  if (!Number.isInteger(n)) return few;
  const abs = Math.abs(n);
  const d10 = abs % 10;
  const d100 = abs % 100;
  if (d10 === 1 && d100 !== 11) return one;
  if (d10 >= 2 && d10 <= 4 && (d100 < 12 || d100 > 14)) return few;
  return many;
}
