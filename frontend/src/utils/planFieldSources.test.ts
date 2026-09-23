import { describe, it, expect } from 'vitest';
import {
  fieldIdHint, moveEntry, parsePlanFieldSetting, serializePlanFieldSetting,
} from './planFieldSources';

describe('parsePlanFieldSetting', () => {
  it('пусто', () => {
    expect(parsePlanFieldSetting(null)).toEqual([]);
    expect(parsePlanFieldSetting(undefined)).toEqual([]);
    expect(parsePlanFieldSetting('  ')).toEqual([]);
  });

  it('старая строка = одно поле-альтернатива', () => {
    expect(parsePlanFieldSetting(' customfield_12431 ')).toEqual([
      { field_id: 'customfield_12431', kind: 'alt', name: null },
    ]);
  });

  it('JSON-список: порядок, вид и имя; неизвестный вид — альтернатива', () => {
    const raw = JSON.stringify([
      { field_id: 'customfield_12888', kind: 'sum', name: 'Оценка Back' },
      { field_id: 'customfield_12432', kind: 'x' },
    ]);
    expect(parsePlanFieldSetting(raw)).toEqual([
      { field_id: 'customfield_12888', kind: 'sum', name: 'Оценка Back' },
      { field_id: 'customfield_12432', kind: 'alt', name: null },
    ]);
  });

  it('мусор и повторы пропускаются, как на сервере', () => {
    const raw = JSON.stringify([
      null, 'cf_0', { kind: 'sum' }, { field_id: '  ' },
      { field_id: 'cf_1', kind: 'sum', name: 'A' },
      { field_id: 'cf_1', kind: 'alt', name: 'B' },
    ]);
    expect(parsePlanFieldSetting(raw)).toEqual([
      { field_id: 'cf_1', kind: 'sum', name: 'A' },
    ]);
  });

  it('битый JSON и не список', () => {
    expect(parsePlanFieldSetting('[{')).toEqual([]);
    expect(parsePlanFieldSetting('[1, 2]')).toEqual([]);
  });
});

describe('serializePlanFieldSetting', () => {
  it('пустые строки и повторы выкидываются', () => {
    const out = serializePlanFieldSetting([
      { field_id: '', kind: 'alt' },
      { field_id: 'cf_1', kind: 'sum', name: 'A' },
      { field_id: 'cf_1', kind: 'alt' },
      { field_id: 'cf_2', kind: 'alt', name: null },
    ]);
    expect(JSON.parse(out)).toEqual([
      { field_id: 'cf_1', kind: 'sum', name: 'A' },
      { field_id: 'cf_2', kind: 'alt' },
    ]);
  });

  it('ничего не выбрано → пустая строка', () => {
    expect(serializePlanFieldSetting([])).toBe('');
    expect(serializePlanFieldSetting([{ field_id: '', kind: 'alt' }])).toBe('');
  });

  it('разбор записанного даёт то же самое', () => {
    const entries = [
      { field_id: 'cf_1', kind: 'alt' as const, name: 'Анализ (ч)' },
      { field_id: 'cf_2', kind: 'sum' as const, name: 'Оценка Back' },
    ];
    expect(parsePlanFieldSetting(serializePlanFieldSetting(entries))).toEqual(entries);
  });
});

describe('moveEntry', () => {
  it('двигает и не выходит за края', () => {
    expect(moveEntry(['a', 'b', 'c'], 1, -1)).toEqual(['b', 'a', 'c']);
    expect(moveEntry(['a', 'b', 'c'], 1, 1)).toEqual(['a', 'c', 'b']);
    expect(moveEntry(['a', 'b'], 0, -1)).toEqual(['a', 'b']);
    expect(moveEntry(['a', 'b'], 1, 1)).toEqual(['a', 'b']);
  });

  it('не меняет исходный список', () => {
    const list = ['a', 'b'];
    moveEntry(list, 0, 1);
    expect(list).toEqual(['a', 'b']);
  });
});

describe('fieldIdHint', () => {
  it('короткий номер поля вместо служебного префикса', () => {
    expect(fieldIdHint('customfield_12431')).toBe('12431');
    expect(fieldIdHint('timeoriginalestimate')).toBe('timeoriginalestimate');
  });
});
