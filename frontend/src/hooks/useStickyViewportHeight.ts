import { useEffect, useState, type RefObject } from 'react';

/**
 * Высота видимой области для sticky-колонки со своей прокруткой.
 *
 * Меряем реальный контейнер прокрутки, а не окно: в тёмной теме страница
 * листается внутри собственного вьюпорта оболочки, и `100vh` там врёт —
 * нижняя карточка уезжала за край.
 */
export function useStickyViewportHeight(
  ref: RefObject<HTMLElement | null>,
  offset: number,
): number | undefined {
  const [height, setHeight] = useState<number>();

  useEffect(() => {
    const el = ref.current;
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
  }, [ref, offset]);

  return height;
}
