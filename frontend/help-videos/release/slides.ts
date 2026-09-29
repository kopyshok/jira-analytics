// Заставка и финальная карточка сводного ролика — отдельные страницы без приложения,
// в цветах тёмной темы. Пункты появляются по одному (CSS-анимация с задержкой).

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const BASE_CSS = `
  * { box-sizing: border-box; margin: 0; }
  html, body { width: 100%; height: 100%; background: #070a12; }
  body {
    display: flex; align-items: center; justify-content: center;
    font-family: Manrope, 'Segoe UI', system-ui, sans-serif; color: #e8edf7;
    background:
      radial-gradient(1100px 700px at 15% 10%, rgba(0, 201, 200, 0.16), transparent 60%),
      radial-gradient(900px 600px at 90% 95%, rgba(124, 92, 255, 0.16), transparent 60%),
      #070a12;
  }
  .wrap { width: 1280px; }
  .brand { font-size: 22px; letter-spacing: 0.32em; text-transform: uppercase; color: #00c9c8; font-weight: 700;
    opacity: 0; animation: in 700ms ease forwards; }
  h1 { font-size: 76px; line-height: 1.1; font-weight: 800; margin-top: 18px;
    opacity: 0; animation: in 800ms ease 250ms forwards; }
  h1 .v { color: #00c9c8; }
  .sub { font-size: 28px; color: #9aa6bd; margin-top: 18px; opacity: 0; animation: in 700ms ease 600ms forwards; }
  ol, ul { list-style: none; padding: 0; margin-top: 44px; display: grid; gap: 14px; }
  li { display: flex; align-items: baseline; gap: 22px; font-size: 32px; line-height: 1.3; font-weight: 600;
    opacity: 0; transform: translateX(-24px); animation: slide 520ms ease forwards; }
  li .n { flex: 0 0 56px; text-align: right; font-size: 28px; color: #00c9c8; font-variant-numeric: tabular-nums; }
  li .dot { flex: 0 0 14px; width: 14px; height: 14px; border-radius: 50%; background: #00c9c8; transform: translateY(-4px); }
  .foot { margin-top: 48px; font-size: 30px; color: #c8d1e3; opacity: 0; animation: in 700ms ease forwards; }
  .foot b { color: #00c9c8; font-weight: 700; }
  @keyframes in { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
  @keyframes slide { to { opacity: 1; transform: none; } }
`;

/** Сколько длится показ пунктов: первый появляется через `startMs`, дальше — каждые `stepMs`. */
function items(list: string[], marker: (i: number) => string, startMs: number, stepMs: number): string {
  return list
    .map((text, i) => `<li style="animation-delay:${startMs + i * stepMs}ms">${marker(i)}<span>${esc(text)}</span></li>`)
    .join('');
}

/** Заставка: название релиза и оглавление глав. */
export function introHtml(release: string, chapters: string[]): string {
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>${BASE_CSS}</style></head><body>
    <div class="wrap">
      <div class="brand">Jira Analytics</div>
      <h1>Что нового в версии <span class="v">${esc(release)}</span></h1>
      <div class="sub">Коротко о главном — по ходу планирования квартала</div>
      <ol>${items(chapters, (i) => `<span class="n">${i + 1}</span>`, 1300, 380)}</ol>
    </div>
  </body></html>`;
}

/** Финал: остальные улучшения списком и куда смотреть подробности. */
export function outroHtml(release: string, more: string[], fixes: number): string {
  const footDelay = 900 + more.length * 450 + 300;
  const fixesText = fixes > 0 ? ` и ${fixes} ${plural(fixes, 'исправление', 'исправления', 'исправлений')}` : '';
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>${BASE_CSS}</style></head><body>
    <div class="wrap">
      <div class="brand">Версия ${esc(release)}</div>
      <h1>А также</h1>
      <ul>${items(more, () => '<span class="dot"></span>', 900, 450)}</ul>
      <div class="foot" style="animation-delay:${footDelay}ms">…${esc(fixesText)}. Подробнее — в окне <b>«Что нового»</b></div>
    </div>
  </body></html>`;
}

export function plural(n: number, one: string, few: string, many: string): string {
  const d10 = n % 10;
  const d100 = n % 100;
  if (d10 === 1 && d100 !== 11) return one;
  if (d10 >= 2 && d10 <= 4 && (d100 < 12 || d100 > 14)) return few;
  return many;
}
