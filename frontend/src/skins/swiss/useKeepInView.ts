import { useEffect, useState } from 'react';

/** Место открытой панели подробностей («bottom» / «right»), пока она открыта; иначе null. */
function useSheetPlacement(): string | null {
  const [placement, setPlacement] = useState(() => document.documentElement.dataset.detailSheet ?? null);
  useEffect(() => {
    const root = document.documentElement;
    const observer = new MutationObserver(() => setPlacement(root.dataset.detailSheet ?? null));
    observer.observe(root, { attributes: true, attributeFilter: ['data-detail-sheet'] });
    return () => observer.disconnect();
  }, []);
  return placement;
}

/**
 * Рабочая область ужимается под панель подробностей — выбранный на странице объект
 * (фаза, строка задачи, счётчик) остаётся на виду: при выборе другого и при смене места панели.
 * `key` — что выбрано сейчас (null — ничего), `selector` — где этот объект на странице.
 */
export function useKeepInView(key: string | null | undefined, selector: string) {
  const placement = useSheetPlacement();
  useEffect(() => {
    if (!key || !placement) return;
    const frame = requestAnimationFrame(() =>
      document.querySelector(selector)?.scrollIntoView({ block: 'nearest', inline: 'nearest' }));
    return () => cancelAnimationFrame(frame);
  }, [key, selector, placement]);
}
