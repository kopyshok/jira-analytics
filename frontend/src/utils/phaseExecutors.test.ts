import { describe, expect, it } from 'vitest';
import { splitByExecutor } from './phaseExecutors';

const part = (id: string, employee_id: string | null, start_date: string | null, part_number = 1) =>
  ({ id, employee_id, start_date, part_number });

describe('splitByExecutor', () => {
  it('один исполнитель — одна строка, как раньше', () => {
    const list = [part('a', 'e1', '2026-10-05', 1), part('b', 'e1', '2026-11-02', 2)];
    expect(splitByExecutor(list)).toEqual([list]);
  });

  it('части разных исполнителей — строка на человека, по первому началу', () => {
    // OS-92133: Шутов — части 1, 2, Кирилов — части 3, 4 (позже).
    const s1 = part('s1', 'shutov', '2026-10-05', 1);
    const s2 = part('s2', 'shutov', '2026-10-26', 2);
    const k3 = part('k3', 'kirilov', '2026-10-19', 3);
    const k4 = part('k4', 'kirilov', '2026-10-26', 4);
    expect(splitByExecutor([k4, s2, k3, s1]).map((r) => r.map((a) => a.id)))
      .toEqual([['s1', 's2'], ['k3', 'k4']]);
  });

  it('части без исполнителя и без дат — отдельной строкой в конце', () => {
    const rows = splitByExecutor([
      part('x', null, null, 3), part('a', 'e1', '2026-10-05', 1), part('b', 'e2', null, 2),
    ]);
    expect(rows.map((r) => r.map((a) => a.id))).toEqual([['a'], ['b'], ['x']]);
  });
});
