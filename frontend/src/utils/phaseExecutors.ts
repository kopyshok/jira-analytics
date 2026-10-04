interface PartLike {
  employee_id: string | null;
  start_date: string | null;
  part_number?: number | null;
}

/**
 * Части одной фазы по исполнителям: у каждого человека — своя строка графика.
 * Один исполнитель — одна строка, как раньше. Строки — по первому началу
 * части; без дат — после датированных, части без исполнителя — в конце.
 */
export function splitByExecutor<T extends PartLike>(parts: T[]): T[][] {
  const groups = new Map<string | null, T[]>();
  for (const p of parts) {
    const list = groups.get(p.employee_id);
    if (list) list.push(p);
    else groups.set(p.employee_id, [p]);
  }
  if (groups.size <= 1) return [parts];
  const firstStart = (list: T[]) =>
    list.reduce<string>((min, p) => (p.start_date && p.start_date < min ? p.start_date : min), '9999-12-31');
  const firstPart = (list: T[]) => Math.min(...list.map((p) => p.part_number ?? 1));
  return [...groups.entries()]
    .sort(([ea, a], [eb, b]) =>
      Number(ea === null) - Number(eb === null)
      || firstStart(a).localeCompare(firstStart(b))
      || firstPart(a) - firstPart(b))
    .map(([, list]) => [...list].sort((x, y) => (x.part_number ?? 1) - (y.part_number ?? 1)));
}
