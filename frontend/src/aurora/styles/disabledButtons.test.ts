// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import source from './antdGlass.css?raw';

// Светлая Aurora перекрашивает основную и обычную кнопку правилами с !important —
// и раньше заодно перекрашивала выключенные: «Построить» в сводке руководителя
// без ИИ выглядела рабочей синей кнопкой. Нужна своя запись для выключенного вида.
const css = source.replace(/\/\*[\s\S]*?\*\//g, '');

// В файле нет вложенных блоков (@media и т.п.) — правило = «селектор { объявления }».
const rules = Array.from(css.matchAll(/([^{}]+)\{([^{}]*)\}/g), (m) => ({
  selector: m[1].trim(),
  decls: Object.fromEntries(
    m[2].split(';').map((d) => d.trim()).filter(Boolean).map((d) => {
      const i = d.indexOf(':');
      return [d.slice(0, i).trim(), d.slice(i + 1).trim()];
    }),
  ) as Record<string, string>,
}));

function button(mode: 'light' | 'dark', kind: 'primary' | 'default', disabled: boolean): HTMLButtonElement {
  document.documentElement.setAttribute('data-theme', 'aurora');
  document.documentElement.setAttribute('data-mode', mode);
  const b = document.createElement('button');
  b.className = `ant-btn ant-btn-${kind}`;
  b.disabled = disabled;
  document.body.appendChild(b);
  return b;
}

const safeMatches = (el: Element, selector: string) => {
  try { return el.matches(selector); } catch { return false; }
};

const important = (v: string | undefined) => !!v && v.endsWith('!important');

/** Правила, которые задают кнопке выключенный вид: без выпуклой тени и без акцента. */
const disabledLook = (el: Element) => rules.filter(({ selector, decls }) =>
  safeMatches(el, selector)
  && important(decls['box-shadow']) && decls['box-shadow'].startsWith('none')
  && important(decls.color)
  && important(decls.background) && !/accent|#3b6ef5|gradient/.test(decls.background));

describe('выключенные кнопки в светлой Aurora', () => {
  it('правила файла разобраны', () => {
    expect(rules.length).toBeGreaterThan(50);
  });

  it.each(['primary', 'default'] as const)('выключенная %s-кнопка получает свой вид', (kind) => {
    expect(disabledLook(button('light', kind, true))).not.toHaveLength(0);
  });

  it.each(['primary', 'default'] as const)('включённая %s-кнопка — без изменений', (kind) => {
    expect(disabledLook(button('light', kind, false))).toHaveLength(0);
  });

  it('тёмная Aurora не затронута', () => {
    expect(disabledLook(button('dark', 'primary', true))).toHaveLength(0);
    expect(disabledLook(button('dark', 'default', true))).toHaveLength(0);
  });
});
