// «Режиссёр» роликов: слой поверх страницы, который попадает в кадр —
// нарисованный курсор, рамка вокруг элемента и подпись внизу экрана.
// Слой не перехватывает клики (pointer-events: none) и лежит выше модальных
// окон, выпадающих списков и панелей (максимальный z-index).
import type { Locator, Page } from '@playwright/test';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/** Куда кладутся готовые ролики и обложки (попадают в сборку как статика). */
const OUT_DIR = fileURLToPath(new URL('../public/help-videos/', import.meta.url));

/** Сколько минимум держится подпись, прежде чем её сменит следующая. */
const MIN_CAPTION_MS = 2200;
/** Время переезда курсора (совпадает с CSS-переходом в слое). */
const TRAVEL_MS = 600;

type Rect = { x: number; y: number; width: number; height: number };

type Overlay = {
  move: (x: number, y: number) => void;
  ring: (rect: Rect | null) => void;
  press: () => void;
  caption: (text: string, variant: 'bar' | 'title') => void;
};

declare global {
  interface Window {
    __director?: Overlay;
  }
}

/** Код слоя; сериализуется в страницу через addInitScript — без внешних ссылок. */
function overlayScript() {
  if (window.top !== window || window.__director) return;

  // Тёмный фон до загрузки стилей приложения: dev-сервер подключает CSS из скриптов,
  // и без этого первые кадры записи — белая вспышка. Скрипт выполняется, когда
  // документ ещё пуст, поэтому при необходимости ждём появления корня страницы.
  const early = document.createElement('style');
  early.textContent = 'html { background: #070a12; }';
  const attachEarly = () => !!document.documentElement?.appendChild(early);
  if (!attachEarly()) {
    const observer = new MutationObserver(() => {
      if (attachEarly()) observer.disconnect();
    });
    observer.observe(document, { childList: true });
  }

  const css = `
    #__director { position: fixed; inset: 0; pointer-events: none; z-index: 2147483647; }
    #__director * { pointer-events: none; box-sizing: border-box; }
    #__director .d-scrim { position: fixed; inset: 0; background: rgba(6, 8, 14, 0.7);
      opacity: 0; transition: opacity 300ms ease; }
    #__director .d-scrim.show { opacity: 1; }
    #__director .d-ring { position: fixed; left: 0; top: 0; width: 0; height: 0; border-radius: 10px;
      border: 3px solid #ffd21f; box-shadow: 0 0 0 4px rgba(255, 210, 31, 0.28), 0 0 22px rgba(255, 210, 31, 0.45);
      opacity: 0; transition: opacity 200ms ease, left 300ms ease, top 300ms ease, width 300ms ease, height 300ms ease; }
    #__director .d-ring.show { opacity: 1; }
    #__director .d-cursor { position: fixed; left: 0; top: 0; width: 0; height: 0;
      transform: translate(720px, 450px); transition: transform 600ms cubic-bezier(0.45, 0, 0.25, 1);
      opacity: 0; }
    #__director .d-cursor.show { opacity: 1; }
    #__director .d-dot { position: absolute; left: -12px; top: -12px; width: 24px; height: 24px; border-radius: 50%;
      background: rgba(255, 210, 31, 0.65); border: 3px solid #ffffff;
      box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.6), 0 4px 14px rgba(0, 0, 0, 0.5); transition: transform 120ms ease; }
    #__director .d-dot.pressed { transform: scale(0.7); }
    #__director .d-ripple { position: absolute; left: -12px; top: -12px; width: 24px; height: 24px; border-radius: 50%;
      border: 3px solid #ffd21f; opacity: 0; }
    #__director .d-ripple.go { animation: d-ripple 500ms ease-out; }
    @keyframes d-ripple { from { opacity: 0.9; transform: scale(1); } to { opacity: 0; transform: scale(2.6); } }
    #__director .d-caption { position: fixed; left: 50%; bottom: 40px; width: max-content; max-width: 80vw;
      transform: translate(-50%, 12px); padding: 14px 30px; border-radius: 14px;
      background: rgb(12, 14, 22); border: 1px solid rgba(255, 255, 255, 0.16); color: #ffffff;
      font: 600 24px/1.35 Manrope, 'Segoe UI', system-ui, sans-serif; text-align: center;
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45); opacity: 0; transition: opacity 220ms ease, transform 220ms ease; }
    #__director .d-caption.show { opacity: 1; transform: translate(-50%, 0); }
    #__director .d-caption.title { bottom: auto; top: 50%; transform: translate(-50%, -40%);
      font-size: 44px; padding: 28px 56px; border-radius: 20px; }
    #__director .d-caption.title.show { transform: translate(-50%, -50%); }
  `;

  let cursor: HTMLElement | null = null;
  let dot: HTMLElement | null = null;
  let ripple: HTMLElement | null = null;
  let ring: HTMLElement | null = null;
  let caption: HTMLElement | null = null;
  let scrim: HTMLElement | null = null;

  const mount = () => {
    if (document.getElementById('__director')) return;
    const root = document.createElement('div');
    root.id = '__director';
    root.innerHTML =
      `<style>${css}</style><div class="d-scrim"></div><div class="d-ring"></div>` +
      '<div class="d-cursor"><div class="d-ripple"></div><div class="d-dot"></div></div>' +
      '<div class="d-caption"></div>';
    document.body.appendChild(root);
    scrim = root.querySelector('.d-scrim');
    ring = root.querySelector('.d-ring');
    cursor = root.querySelector('.d-cursor');
    dot = root.querySelector('.d-dot');
    ripple = root.querySelector('.d-ripple');
    caption = root.querySelector('.d-caption');
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();

  window.__director = {
    move(x, y) {
      if (!cursor) return;
      cursor.classList.add('show');
      cursor.style.transform = `translate(${x}px, ${y}px)`;
    },
    ring(rect) {
      if (!ring) return;
      if (!rect) {
        ring.classList.remove('show');
        return;
      }
      const pad = 5;
      ring.style.left = `${rect.x - pad}px`;
      ring.style.top = `${rect.y - pad}px`;
      ring.style.width = `${rect.width + pad * 2}px`;
      ring.style.height = `${rect.height + pad * 2}px`;
      ring.classList.add('show');
    },
    press() {
      if (!dot || !ripple) return;
      const d = dot;
      const r = ripple;
      d.classList.add('pressed');
      r.classList.remove('go');
      void r.offsetWidth;
      r.classList.add('go');
      setTimeout(() => d.classList.remove('pressed'), 180);
    },
    caption(text, variant) {
      if (!caption || !scrim) return;
      const c = caption;
      const s = scrim;
      c.classList.remove('show');
      s.classList.toggle('show', variant === 'title');
      setTimeout(() => {
        c.textContent = text;
        c.classList.toggle('title', variant === 'title');
        c.classList.add('show');
      }, 180);
    },
  };
}

export class Director {
  private captionAt = 0;
  private posterJpeg: Buffer | null = null;

  constructor(private readonly page: Page) {}

  /**
   * Подключить слой (переживает переходы между страницами) и закрасить пустую
   * страницу тёмным: запись идёт с момента создания окна, без белой вспышки.
   */
  async install(): Promise<void> {
    await this.page.addInitScript(overlayScript);
    await this.page.setContent('<body style="margin:0;background:#070a12"></body>');
  }

  /** Открыть страницу ролика; заголовок по центру закрывает её загрузку. */
  async open(path: string, title: string): Promise<void> {
    await this.page.goto(path);
    // Без слоя ролик снялся бы без подписей и курсора — это ошибка, а не тихий пропуск.
    await this.page.locator('#__director .d-caption').waitFor({ state: 'attached', timeout: 5_000 });
    await this.showCaption(title, 'title');
  }

  pause(ms: number): Promise<void> {
    return this.page.waitForTimeout(ms);
  }

  /** Подпись внизу экрана. Предыдущая подпись успевает провисеть MIN_CAPTION_MS. */
  async caption(text: string, holdMs = 0): Promise<void> {
    await this.showCaption(text, 'bar');
    if (holdMs) await this.pause(holdMs);
  }

  /** Плавно подвести курсор к центру элемента и обвести его рамкой. */
  async point(locator: Locator): Promise<void> {
    await this.aim(locator, undefined, false);
  }

  /**
   * Показать результат: обвести элемент (или полосу от `locator` до `to`),
   * курсор встаёт сбоку снизу, чтобы не закрывать содержимое.
   */
  async show(locator: Locator, to?: Locator): Promise<void> {
    await this.aim(locator, to, true);
  }

  /** Подвести курсор, дать зрителю увидеть цель, «нажать» и кликнуть по-настоящему. */
  async click(locator: Locator, caption?: string): Promise<void> {
    if (caption) await this.caption(caption);
    await this.point(locator);
    await this.pause(700);
    await this.page.evaluate(() => window.__director?.press());
    await this.pause(160);
    await locator.click();
    await this.page.evaluate(() => window.__director?.ring(null));
    await this.pause(650);
  }

  /** Кликнуть в поле и набрать текст с видимой скоростью. */
  async type(locator: Locator, text: string, caption?: string): Promise<void> {
    await this.click(locator, caption);
    await locator.pressSequentially(text, { delay: 90 });
    await this.pause(600);
  }

  /** Запомнить текущий кадр как обложку ролика (пишется в файл вместе с роликом). */
  async poster(): Promise<void> {
    this.posterJpeg = await this.page.screenshot({ type: 'jpeg', quality: 80 });
  }

  /**
   * Закрыть страницу и сохранить public/help-videos/<id>.webm и <id>.jpg.
   * Вызывается в конце сценария: упавшая съёмка не затирает готовые файлы.
   */
  async save(id: string): Promise<void> {
    const video = this.page.video();
    if (!video) throw new Error('Запись видео не включена в конфигурации');
    if (!this.posterJpeg) throw new Error('Не снята обложка: вызовите poster()');
    await this.page.close();
    await video.saveAs(`${OUT_DIR}${id}.webm`);
    writeFileSync(`${OUT_DIR}${id}.jpg`, this.posterJpeg);
  }

  private async aim(locator: Locator, to: Locator | undefined, aside: boolean): Promise<void> {
    await locator.scrollIntoViewIfNeeded();
    const box = await boxOf(locator);
    if (to) {
      const end = await boxOf(to);
      const right = Math.max(box.x + box.width, end.x + end.width);
      const bottom = Math.max(box.y + box.height, end.y + end.height);
      box.x = Math.min(box.x, end.x);
      box.y = Math.min(box.y, end.y);
      box.width = right - box.x;
      box.height = bottom - box.y;
    }
    const x = aside ? box.x + box.width - 10 : box.x + box.width / 2;
    const y = aside ? box.y + box.height + 16 : box.y + box.height / 2;
    await this.page.evaluate((at) => {
      window.__director?.ring(at.rect);
      window.__director?.move(at.x, at.y);
    }, { rect: box, x, y });
    await this.pause(TRAVEL_MS + 150);
  }

  private async showCaption(text: string, variant: 'bar' | 'title'): Promise<void> {
    await this.waitCaptionMin();
    await this.page.evaluate(([t, v]) => window.__director?.caption(t, v as 'bar' | 'title'), [text, variant]);
    this.captionAt = Date.now();
  }

  private async waitCaptionMin(): Promise<void> {
    if (!this.captionAt) return;
    const left = MIN_CAPTION_MS - (Date.now() - this.captionAt);
    if (left > 0) await this.pause(left);
  }
}

async function boxOf(locator: Locator): Promise<Rect> {
  const box = await locator.boundingBox();
  if (!box) throw new Error(`Элемент не виден на экране: ${locator}`);
  return box;
}
