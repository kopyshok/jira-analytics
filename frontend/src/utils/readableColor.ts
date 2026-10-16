/**
 * Читаемые цвета для справочных цветов из базы (роли, виды работ, причины
 * отсутствий, аватары). Сохранённый цвет бывает любым — от бледно-голубого до
 * насыщенного розового, и текст прямо на нём или им на белом не читается.
 * В светлых скинах из него делается пара «светлая подложка того же оттенка +
 * тёмный текст того же оттенка» с контрастом не ниже 4.5:1.
 */

export interface ReadablePair {
  /** Светлая подложка (метка, аватар, плашка). */
  bg: string;
  /** Тёмный текст того же оттенка на этой подложке. */
  fg: string;
}

const MIN_CONTRAST = 4.6; // с запасом над 4.5 — на округление при отрисовке

type Rgb = [number, number, number];

function parseHex(input: string | null | undefined): Rgb | null {
  if (!input) return null;
  const m = input.trim().match(/^#?([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i);
  if (!m) return null;
  let h = m[1];
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function toHex([r, g, b]: Rgb): string {
  return '#' + [r, g, b].map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')).join('').toUpperCase();
}

function rgbToHsl([r, g, b]: Rgb): [number, number, number] {
  const rn = r / 255, gn = g / 255, bn = b / 255;
  const max = Math.max(rn, gn, bn), min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h: number;
  if (max === rn) h = (gn - bn) / d + (gn < bn ? 6 : 0);
  else if (max === gn) h = (bn - rn) / d + 2;
  else h = (rn - gn) / d + 4;
  return [h * 60, s, l];
}

function hslToRgb(h: number, s: number, l: number): Rgb {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hp = (((h % 360) + 360) % 360) / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let rgb: [number, number, number] = [0, 0, 0];
  if (hp < 1) rgb = [c, x, 0];
  else if (hp < 2) rgb = [x, c, 0];
  else if (hp < 3) rgb = [0, c, x];
  else if (hp < 4) rgb = [0, x, c];
  else if (hp < 5) rgb = [x, 0, c];
  else rgb = [c, 0, x];
  const m = l - c / 2;
  return [(rgb[0] + m) * 255, (rgb[1] + m) * 255, (rgb[2] + m) * 255];
}

function luminance([r, g, b]: Rgb): number {
  const f = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

/** Контраст двух цветов по WCAG (1…21). Неразборчивый цвет — 1. */
export function contrastRatio(a: string, b: string): number {
  const ca = parseHex(a);
  const cb = parseHex(b);
  if (!ca || !cb) return 1;
  const la = luminance(ca);
  const lb = luminance(cb);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Тёплый серый — для пустого или неразборчивого цвета. */
const FALLBACK = '#8A8174';

/**
 * Пара «светлая подложка + тёмный текст» того же оттенка, что и `color`.
 * Контраст текста к подложке ≥ 4.5:1 при любом исходном цвете.
 */
export function readablePair(color: string | null | undefined): ReadablePair {
  const rgb = parseHex(color) ?? parseHex(FALLBACK)!;
  const [h, s] = rgbToHsl(rgb);
  // Серые и почти серые остаются тёплыми нейтральными, а не уходят в случайный оттенок.
  const grey = s < 0.08;
  const bgSat = grey ? 0.14 : Math.min(Math.max(s, 0.3), 0.6);
  const bg = hslToRgb(grey ? 38 : h, bgSat, 0.92);
  const fgSat = grey ? 0.1 : Math.min(Math.max(s, 0.35), 0.7);
  let l = 0.4;
  let fg = hslToRgb(grey ? 38 : h, fgSat, l);
  const bgHex = toHex(bg);
  while (l > 0.08 && contrastRatio(toHex(fg), bgHex) < MIN_CONTRAST) {
    l -= 0.02;
    fg = hslToRgb(grey ? 38 : h, fgSat, l);
  }
  return { bg: bgHex, fg: toHex(fg) };
}

/**
 * Тёмный вариант цвета для текста прямо на белом (подпись, число, ссылка):
 * тот же оттенок, затемнённый до контраста ≥ 4.5:1 к `on` (по умолчанию белый).
 */
export function readableText(color: string | null | undefined, on = '#FFFFFF'): string {
  const rgb = parseHex(color) ?? parseHex(FALLBACK)!;
  if (contrastRatio(toHex(rgb), on) >= MIN_CONTRAST) return toHex(rgb);
  const [h, s, l0] = rgbToHsl(rgb);
  let l = Math.min(l0, 0.5);
  let out = hslToRgb(h, s, l);
  while (l > 0.05 && contrastRatio(toHex(out), on) < MIN_CONTRAST) {
    l -= 0.02;
    out = hslToRgb(h, s, l);
  }
  return toHex(out);
}
