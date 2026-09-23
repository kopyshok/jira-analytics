import { describe, it, expect } from 'vitest';
import type { BacklogChild, BacklogItemResponse, EstimateCandidate } from '../types/api';
import {
  MANUAL_CHOICE, countDisputed, defaultChoice, filterDisputed, formatChoiceHours, hasDispute,
} from './estimateDisputes';

const child = (id: string, disputed = false) =>
  ({ id, disputed_roles: disputed ? ['dev'] : [] }) as unknown as BacklogChild;

const row = (id: string, disputed: boolean, children: BacklogChild[] = []) =>
  ({ id, disputed_roles: disputed ? ['analyst', 'opo'] : [], children }) as unknown as BacklogItemResponse;

const cands: EstimateCandidate[] = [
  { source: 'customfield_1', label: 'Анализ (ч)', value: 40 },
  { source: 'customfield_2', label: 'Оценка SA/PM (ч)', value: 56 },
];

describe('hasDispute', () => {
  it('нет поля или пусто — спора нет', () => {
    expect(hasDispute({})).toBe(false);
    expect(hasDispute({ disputed_roles: [] })).toBe(false);
    expect(hasDispute({ disputed_roles: ['qa'] })).toBe(true);
  });
});

describe('filterDisputed', () => {
  it('спорная строка остаётся только со спорными дочками', () => {
    const out = filterDisputed([row('a', true, [child('a1'), child('a2', true)])]);
    expect(out?.map((r) => [r.id, (r.children ?? []).map((c) => c.id)])).toEqual([['a', ['a2']]]);
  });

  it('родитель без спора остаётся ради спорных дочек, без них — уходит', () => {
    const out = filterDisputed([
      row('b', false, [child('b1', true), child('b2')]),
      row('c', false, [child('c1')]),
      row('d', false),
    ]);
    expect(out?.map((r) => [r.id, (r.children ?? []).map((c) => c.id)])).toEqual([['b', ['b1']]]);
  });

  it('пустой список', () => {
    expect(filterDisputed(undefined)).toBeUndefined();
  });
});

describe('countDisputed', () => {
  it('считает задачи: и строки, и дочерние строки', () => {
    expect(countDisputed([
      row('a', true, [child('a1', true), child('a2')]),
      row('b', false, [child('b1', true)]),
      row('c', false),
    ])).toBe(3);
    expect(countDisputed(undefined)).toBe(0);
  });
});

describe('defaultChoice', () => {
  it('отмечено поле, значение которого сейчас действует', () => {
    expect(defaultChoice(cands, 56)).toEqual({ picked: 'customfield_2', manual: null });
    expect(defaultChoice(cands, 40.0000001)).toEqual({ picked: 'customfield_1', manual: null });
  });

  it('действует ручная правка — отмечено «своё» с этим значением', () => {
    expect(defaultChoice(cands, 70)).toEqual({ picked: MANUAL_CHOICE, manual: 70 });
    expect(defaultChoice(cands, 0)).toEqual({ picked: MANUAL_CHOICE, manual: 0 });
  });

  it('значения нет — первое поле', () => {
    expect(defaultChoice(cands, null)).toEqual({ picked: 'customfield_1', manual: null });
    expect(defaultChoice([], undefined)).toEqual({ picked: MANUAL_CHOICE, manual: null });
  });
});

describe('formatChoiceHours', () => {
  it('целые без дробной части, дробные — до сотых', () => {
    expect(formatChoiceHours(40)).toBe('40');
    expect(formatChoiceHours(12.5)).toBe('12.5');
    expect(formatChoiceHours(12.3333)).toBe('12.33');
  });
});
