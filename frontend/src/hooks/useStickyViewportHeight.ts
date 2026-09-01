import { useEffect, useState } from 'react';

/**
 * Высота видимой области для sticky-колонки со своей прокруткой.
 *
 * На вход — сам узел, а не ref: колонка появляется только после загрузки
 * сценария, и замер по ref успевал отработать вхолостую по пустой ссылке.
 *
 * Меряем реальный контейнер прокрутки, а не окно: в тёмной теме страница
 * листается внутри собственного вьюпорта оболочки, и `100vh` там врёт —
 * нижняя карточка уезжала за край.
 */
export function useStickyViewportHeight(
  el: HTMLElement | null,
  offset: number,
): number | undefined {
  const [height, setHeight] = useState<number>();

  useEffect(() => {
    if (!el) return;

    let scroller: HTMLElement | null = null;
    for (let p = el.parentElement; p; p = p.parentElement) {
      const overflow = getComputedStyle(p).overflowY;
      if (overflow === 'auto' || overflow === 'scroll') {
        scroller = p;
        break;
      }
    }

    const measure = () => {
      const viewport = scroller ? scroller.clientHeight : window.innerHeight;
      setHeight(Math.max(240, viewport - offset));
    };
    measure();

    const observer = new ResizeObserver(measure);
    observer.observe(scroller ?? document.documentElement);
    window.addEventListener('resize', measure);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [el, offset]);

  return height;
}
