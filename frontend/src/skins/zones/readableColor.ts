/**
 * Читаемая пара цветов для меток из справочников (роли, виды работ, причины
 * отсутствия, аватары): цвет в базе бывает любым — пастельным, неоновым,
 * белым. В скине «Цветовые зоны» такая метка рисуется светлой подложкой того
 * же оттенка и тёмным текстом того же оттенка с контрастом не ниже 4.5:1.
 */

export interface ReadablePair {
  /** Светлая подложка того же оттенка. */
  bg: string;
  /** Тёмный текст того же оттенка, контраст с подложкой ≥ 4.5. */
  fg: string;
  /** Рамка — между подложкой и текстом. */
  border: string;
}

interface Rgb { r: number; g: number; b: number }

const NEUTRAL: Rgb = { r: 0x7b, g: 0x80, b: 0x88 };

function parseHex(input: string | null | undefined): Rgb | null {
  if (!input) return null;
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(input.trim());
  if (!m) return null;
  const h = m[1].length === 3 ? m[1].split('').map((c) => c + c).join('') : m[1];
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  };
}

function toHex({ r, g, b }: Rgb): string {
  const c = (v: number) => Math.round(Math.min(255, Math.max(0, v))).toString(16).padStart(2, '0');
  return `#${c(r)}${c(g)}${c(b)}`.toUpperCase();
}

function rgbToHsl({ r, g, b }: Rgb): [number, number, number] {
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
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x]
    : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return { r: (r + m) * 255, g: (g + m) * 255, b: (b + m) * 255 };
}

function luminance({ r, g, b }: Rgb): number {
  const f = (v: number) => {
    const n = v / 255;
    return n <= 0.03928 ? n / 12.92 : Math.pow((n + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

/** Контраст двух цветов по WCAG (1…21). */
export function contrastRatio(a: string, b: string): number {
  const ca = parseHex(a), cb = parseHex(b);
  if (!ca || !cb) return 1;
  const la = luminance(ca), lb = luminance(cb);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/**
 * Подложка и текст одного оттенка для метки с цветом из справочника.
 * Неразборчивый цвет (пусто, не hex) — нейтральный серый.
 */
export function readablePair(color: string | null | undefined): ReadablePair {
  const rgb = parseHex(color) ?? NEUTRAL;
  const [h, s0] = rgbToHsl(rgb);
  // Почти серые цвета (белый, бежевый фон) — нейтральная пара без оттенка:
  // смотрим на разброс каналов, насыщенность HSL у светлых цветов обманчива.
  const chroma = (Math.max(rgb.r, rgb.g, rgb.b) - Math.min(rgb.r, rgb.g, rgb.b)) / 255;
  const s = chroma < 0.1 ? 0 : Math.min(s0, 0.72);
  const bg = toHex(hslToRgb(h, s === 0 ? 0 : Math.min(s, 0.6), 0.94));
  const border = toHex(hslToRgb(h, s === 0 ? 0 : Math.min(s, 0.5), 0.8));
  // Текст темнеет, пока не наберёт 4.5 к подложке (и к белому — метка
  // может стоять и без подложки).
  let l = 0.36;
  let fg = toHex(hslToRgb(h, s, l));
  while ((contrastRatio(fg, bg) < 4.5 || contrastRatio(fg, '#FFFFFF') < 4.5) && l > 0.08) {
    l -= 0.02;
    fg = toHex(hslToRgb(h, s, l));
  }
  return { bg, fg, border };
}
