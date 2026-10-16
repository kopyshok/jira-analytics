/**
 * Читаемые пары цветов для обложек поверх светлой темы.
 *
 * Цвета справочников (роли, виды работ, причины отсутствий, аватары) хранятся
 * в базе и подбирались под тёмную тему: пастельный текст на пастельной
 * подложке не читается. Здесь любой цвет превращается в пару «светлая
 * подложка + тёмный текст того же оттенка» с контрастом не ниже 4.5:1.
 */

export interface Rgb { r: number; g: number; b: number }

export interface ReadablePair {
  /** Светлая подложка того же оттенка. */
  bg: string;
  /** Тёмный текст того же оттенка, контраст к bg ≥ 4.5:1. */
  fg: string;
  /** Рамка — между подложкой и текстом. */
  border: string;
}

const NEUTRAL: Rgb = { r: 154, g: 151, b: 143 };

/** «#abc», «#aabbcc», «rgb(1, 2, 3)» → цвет; непонятное — null. */
export function parseColor(input: string | null | undefined): Rgb | null {
  if (!input) return null;
  const s = input.trim();
  const hex = s.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    const h = hex[1].length === 3 ? hex[1].split('').map((c) => c + c).join('') : hex[1];
    return { r: parseInt(h.slice(0, 2), 16), g: parseInt(h.slice(2, 4), 16), b: parseInt(h.slice(4, 6), 16) };
  }
  const rgb = s.match(/^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/i);
  if (rgb) return { r: +rgb[1], g: +rgb[2], b: +rgb[3] };
  return null;
}

export function toHex({ r, g, b }: Rgb): string {
  const c = (v: number) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0');
  return `#${c(r)}${c(g)}${c(b)}`.toUpperCase();
}

function luminance({ r, g, b }: Rgb): number {
  const f = (v: number) => {
    const x = v / 255;
    return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

/** Контраст двух цветов по WCAG (1…21). */
export function contrastRatio(a: Rgb, b: Rgb): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

function toHsl({ r, g, b }: Rgb): [number, number, number] {
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
  return [h / 6, s, l];
}

function fromHsl(h: number, s: number, l: number): Rgb {
  if (s === 0) return { r: l * 255, g: l * 255, b: l * 255 };
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const hue = (t: number) => {
    let x = t;
    if (x < 0) x += 1;
    if (x > 1) x -= 1;
    if (x < 1 / 6) return p + (q - p) * 6 * x;
    if (x < 1 / 2) return q;
    if (x < 2 / 3) return p + (q - p) * (2 / 3 - x) * 6;
    return p;
  };
  return { r: hue(h + 1 / 3) * 255, g: hue(h) * 255, b: hue(h - 1 / 3) * 255 };
}

function mix(a: Rgb, b: Rgb, t: number): Rgb {
  return { r: a.r + (b.r - a.r) * t, g: a.g + (b.g - a.g) * t, b: a.b + (b.b - a.b) * t };
}

const WHITE: Rgb = { r: 255, g: 255, b: 255 };

/**
 * Тот же оттенок, затемнённый до контраста `min` к фону `on`.
 * Для цветного текста (ключи задач, имена) на светлых поверхностях.
 */
export function readableInk(color: string | null | undefined, on = '#FFFFFF', min = 4.6): string {
  const base = parseColor(color) ?? NEUTRAL;
  const bg = parseColor(on) ?? WHITE;
  if (contrastRatio(base, bg) >= min) return toHex(base);
  const [h, s0, l0] = toHsl(base);
  const s = Math.min(s0, 0.78);
  for (let l = Math.min(l0, 0.5); l >= 0; l -= 0.02) {
    const c = fromHsl(h, s, l);
    if (contrastRatio(c, bg) >= min) return toHex(c);
  }
  return '#1C1C1A';
}

/** Пара «светлая подложка + тёмный текст» того же оттенка для фишек и аватаров. */
export function readablePair(color: string | null | undefined): ReadablePair {
  const base = parseColor(color) ?? NEUTRAL;
  const bg = mix(base, WHITE, 0.84);
  const bgHex = toHex(bg);
  return {
    bg: bgHex,
    fg: readableInk(toHex(base), bgHex, 4.6),
    border: toHex(mix(base, WHITE, 0.55)),
  };
}

/** Цвет надписи поверх сплошной заливки: тёмный или белый — какой контрастнее. */
export function textOnFill(fill: string | null | undefined): '#1C1C1A' | '#FFFFFF' {
  const c = parseColor(fill) ?? NEUTRAL;
  const dark: Rgb = { r: 28, g: 28, b: 26 };
  return contrastRatio(c, dark) >= contrastRatio(c, WHITE) ? '#1C1C1A' : '#FFFFFF';
}
