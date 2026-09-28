export interface TourStepDef {
  /** Значение атрибута data-tour у элемента; null — окно по центру экрана. */
  target: string | null;
  title: string;
  description: string;
  /** data-tour элемента, по которому кликнуть перед шагом (переключить вкладку). */
  clickFirst?: string;
}

export interface TourDef {
  id: string;
  /** Куда перейти перед экскурсией; нет — остаться на текущей странице. */
  route?: string;
  steps: TourStepDef[];
}

export const TOURS: Record<string, TourDef> = {};
