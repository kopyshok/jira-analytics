import { describe, expect, it } from 'vitest';
import { contrastRatio, readablePair, readableText } from '../readableColor';

// Цвета, которые реально лежат в справочниках и давали нечитаемый текст.
const SAMPLES = [
  '#9bd7f2', '#f48bc4', '#78a49a', '#eb2f96', '#00c9c8', '#5470ff', '#a070ff',
  '#3a7bff', '#f59e0b', '#52d364', '#ffffff', '#000000', '#6b7280', '#ff9c4a',
  '#b5502a', '#f5f1ea', '#fadb14', '#13c2c2', '#722ed1', '#808080',
];

describe('contrastRatio', () => {
  it('чёрный на белом — 21', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 0);
  });
  it('одинаковые цвета — 1', () => {
    expect(contrastRatio('#2F6B5A', '#2f6b5a')).toBeCloseTo(1, 5);
  });
  it('неразборчивый цвет — 1', () => {
    expect(contrastRatio('red', '#ffffff')).toBe(1);
  });
});

describe('readablePair', () => {
  it.each(SAMPLES)('текст на подложке читается для %s', (hex) => {
    const { bg, fg } = readablePair(hex);
    expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(4.5);
  });

  it('подложка светлая — почти белая', () => {
    for (const hex of SAMPLES) {
      expect(contrastRatio(readablePair(hex).bg, '#ffffff')).toBeLessThan(1.35);
    }
  });

  it('оттенок сохраняется: розовое остаётся розовым', () => {
    const { fg } = readablePair('#f48bc4');
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(fg.slice(i, i + 2), 16));
    expect(r).toBeGreaterThan(g);
    expect(b).toBeGreaterThan(g);
  });

  it('пустой и кривой цвет — тёплая нейтральная пара', () => {
    for (const v of [null, undefined, '', 'rgb(1,2,3)', '#12']) {
      const { bg, fg } = readablePair(v);
      expect(bg).toMatch(/^#[0-9A-F]{6}$/);
      expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('короткая запись #rgb разбирается', () => {
    expect(readablePair('#0cc')).toEqual(readablePair('#00cccc'));
  });
});

describe('readableText', () => {
  it.each(SAMPLES)('текст цвета %s читается на белом', (hex) => {
    expect(contrastRatio(readableText(hex), '#ffffff')).toBeGreaterThanOrEqual(4.5);
  });
  it('уже тёмный цвет не меняется', () => {
    expect(readableText('#2F6B5A')).toBe('#2F6B5A');
  });
});
