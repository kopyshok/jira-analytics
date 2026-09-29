import { describe, expect, it } from 'vitest';
import { formatInvolvement, formatNormed, formatQuarter, roleNormedPercents, sumPercent } from './personalSettings';

describe('formatQuarter', () => {
  it('склеивает квартал и год', () => {
    expect(formatQuarter(2026, 4)).toBe('Q4 2026');
    expect(formatQuarter(2027, 1)).toBe('Q1 2027');
  });
});

describe('formatInvolvement', () => {
  it('не задано — тире', () => {
    expect(formatInvolvement(null)).toBe('—');
  });
  it('доля переводится в проценты и округляется', () => {
    expect(formatInvolvement(1)).toBe('100%');
    expect(formatInvolvement(0.7)).toBe('70%');
    expect(formatInvolvement(0)).toBe('0%');
    expect(formatInvolvement(0.555)).toBe('56%');
  });
});

describe('formatNormed', () => {
  it('по правилам роли — normed_custom=false, список игнорируется', () => {
    expect(formatNormed({ normed_custom: false, normed: [] })).toBe('по правилам роли');
    expect(formatNormed({
      normed_custom: false,
      normed: [{ work_type_id: 'wt1', label: 'Сопровождение', percent_of_norm: 5 }],
    })).toBe('по правилам роли');
  });

  it('свои, но пусто — нет нормированных работ', () => {
    expect(formatNormed({ normed_custom: true, normed: [] })).toBe('нет');
  });

  it('свои проценты — виды и проценты через точку', () => {
    const normed = [
      { work_type_id: 'wt1', label: 'Сопровождение', percent_of_norm: 5 },
      { work_type_id: 'wt2', label: 'Орг. вопросы', percent_of_norm: 10 },
    ];
    expect(formatNormed({ normed_custom: true, normed })).toBe('Сопровождение 5% · Орг. вопросы 10%');
  });
});

describe('sumPercent', () => {
  it('складывает проценты списка', () => {
    expect(sumPercent([{ percent_of_norm: 5 }, { percent_of_norm: 10 }])).toBe(15);
  });
  it('пустой список — 0', () => {
    expect(sumPercent([])).toBe(0);
  });
});

describe('roleNormedPercents', () => {
  const rules = [
    { role: 'dev', work_type_id: 'wt1', percent_of_norm: 55 },
    { role: 'dev', work_type_id: 'wt2', percent_of_norm: 5 },
    { role: null, work_type_id: 'wt1', percent_of_norm: 10 },
    { role: null, work_type_id: 'wt3', percent_of_norm: 2 },
  ];
  const pool = ['wt1', 'wt2', 'wt3'];

  it('есть правила роли — используются они, а не «для всех»', () => {
    expect(roleNormedPercents(rules, 'dev', pool)).toEqual({ wt1: 55, wt2: 5 });
  });

  it('нет своих правил у роли — используются «для всех ролей»', () => {
    expect(roleNormedPercents(rules, 'analyst', pool)).toEqual({ wt1: 10, wt3: 2 });
  });

  it('роль не задана — сразу «для всех ролей»', () => {
    expect(roleNormedPercents(rules, null, pool)).toEqual({ wt1: 10, wt3: 2 });
  });

  it('нет вообще никаких правил — пустая карта', () => {
    expect(roleNormedPercents([], 'dev', pool)).toEqual({});
  });

  it('учитывает только виды, уменьшающие запас — не пул не считается', () => {
    const withNonPool = [
      { role: 'dev', work_type_id: 'wt-other', percent_of_norm: 90 },
      { role: null, work_type_id: 'wt1', percent_of_norm: 10 },
    ];
    // У роли dev есть правило, но не по пуловому виду — значит своих пуловых
    // правил нет, используются «для всех ролей».
    expect(roleNormedPercents(withNonPool, 'dev', pool)).toEqual({ wt1: 10 });
  });

  it('складывает дублирующиеся правила одного вида, а не перезаписывает', () => {
    const dup = [
      { role: 'dev', work_type_id: 'wt1', percent_of_norm: 20 },
      { role: 'dev', work_type_id: 'wt1', percent_of_norm: 15 },
    ];
    expect(roleNormedPercents(dup, 'dev', pool)).toEqual({ wt1: 35 });
  });
});
