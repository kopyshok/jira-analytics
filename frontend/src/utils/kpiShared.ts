import type { KeyboardEvent } from 'react';

/**
 * Общий модуль раздела KPI — статус метрики, короткие названия месяцев и
 * помощник клавиатурной активации ячеек. Раньше `statusOf` был скопирован
 * дословно в `KpiLedger.tsx` и `KpiEmployeeCard.tsx`, а сокращённые русские
 * месяцы объявлены отдельно от общих `MONTH_NAMES` в `utils/constants.ts`
 * (см. ревью, мелочи).
 */

export type KpiStatus = 'good' | 'warn' | 'bad' | 'none';

/** Статус ячейки метрики/итога относительно цели и жёлтой зоны. */
export function kpiStatusOf(value: number | null, target: number | null, warnBand: number | null): KpiStatus {
  if (value == null || target == null) return 'none';
  if (value >= target) return 'good';
  const band = warnBand ?? 10;
  if (value >= target - band) return 'warn';
  return 'bad';
}

export const KPI_MONTH_ABBR_RU = [
  'Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек',
];

/** Клавиатурный обработчик для элементов с `role="button"` и обработчиком клика
 * (Enter/Space активируют, как и настоящую кнопку) — раньше такие ячейки
 * получали фокус по Tab, но ничего не происходило по клавиатуре (см. ревью,
 * мелочи). */
export function onKpiCellActivate(handler: () => void) {
  return (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handler();
    }
  };
}
