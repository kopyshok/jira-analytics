import { useCallback, useRef, useState } from 'react';

/**
 * Ширина элемента — по ней содержимое панели подробностей решает, сколько колонок рисовать.
 * Ссылка-функция: элемент появляется позже (панель открылась) — наблюдение начинается само.
 */
export function useWidth<T extends HTMLElement>(): [(el: T | null) => void, number] {
  const [width, setWidth] = useState(0);
  const observer = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: T | null) => {
    observer.current?.disconnect();
    observer.current = null;
    if (!el) return;
    observer.current = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.current.observe(el);
  }, []);
  return [ref, width];
}
