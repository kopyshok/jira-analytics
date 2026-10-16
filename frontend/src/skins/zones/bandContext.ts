import { createContext, useContext } from 'react';

/**
 * Цветная полоса зоны в скине «Цветовые зоны» несёт заголовок экрана,
 * подзаголовок, глобальные элементы и ряд фильтров/вкладок экрана.
 * Оболочка отдаёт сюда места в полосе, страница переносит в них свои
 * элементы порталом — состояние и обработчики остаются у страницы.
 */
export interface ZonesBandSlots {
  /** Слева в верхнем ряду: рубрика, заголовок, подзаголовок. */
  head: HTMLElement | null;
  /** Справа в верхнем ряду, после глобальных элементов. */
  tools: HTMLElement | null;
  /** Нижние ряды полосы: фильтры, вкладки. */
  rows: HTMLElement | null;
  /** Подпись зоны страницы — рубрика по умолчанию. */
  zoneLabel: string;
}

export const ZonesBandContext = createContext<ZonesBandSlots | null>(null);

/** Места в полосе зоны; null — страница открыта не в оболочке зон. */
export function useZonesBand(): ZonesBandSlots | null {
  return useContext(ZonesBandContext);
}
