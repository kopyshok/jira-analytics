import { describe, expect, it } from 'vitest';
import { nextPersonSort, sortByPerson, type PersonSort } from './allocationSort';

const row = (id: string, a: string | null, d: string | null) => ({
  id,
  assignee_display_name: a,
  developer_display_name: d,
});

describe('nextPersonSort', () => {
  it('цикл: А→Я, Я→А, выкл', () => {
    let s: PersonSort | null = null;
    s = nextPersonSort(s, 'analyst');
    expect(s).toEqual({ key: 'analyst', dir: 'asc' });
    s = nextPersonSort(s, 'analyst');
    expect(s).toEqual({ key: 'analyst', dir: 'desc' });
    s = nextPersonSort(s, 'analyst');
    expect(s).toBeNull();
  });
  it('другой столбец начинает с А→Я', () => {
    expect(nextPersonSort({ key: 'analyst', dir: 'desc' }, 'developer')).toEqual({
      key: 'developer',
      dir: 'asc',
    });
  });
});

describe('sortByPerson', () => {
  const rows = [row('1', 'Яковлев', 'Б'), row('2', null, 'А'), row('3', 'Андреев', null), row('4', '', 'В')];

  it('без сортировки — тот же порядок', () => {
    expect(sortByPerson(rows, null)).toBe(rows);
  });
  it('А→Я, пустые в конце, исходный массив не меняется', () => {
    const out = sortByPerson(rows, { key: 'analyst', dir: 'asc' });
    expect(out.map((r) => r.id)).toEqual(['3', '1', '2', '4']);
    expect(rows.map((r) => r.id)).toEqual(['1', '2', '3', '4']);
  });
  it('Я→А, пустые всё равно в конце', () => {
    const out = sortByPerson(rows, { key: 'analyst', dir: 'desc' });
    expect(out.map((r) => r.id)).toEqual(['1', '3', '2', '4']);
  });
  it('по разработчику', () => {
    const out = sortByPerson(rows, { key: 'developer', dir: 'asc' });
    expect(out.map((r) => r.id)).toEqual(['2', '1', '4', '3']);
  });
  it('регистр и ё не мешают', () => {
    const out = sortByPerson(
      [row('1', 'ёлкин', null), row('2', 'Егоров', null), row('3', 'абрамов', null)],
      { key: 'analyst', dir: 'asc' },
    );
    expect(out.map((r) => r.id)).toEqual(['3', '2', '1']);
  });
});
