import type { TourStepDef } from './tours';

/** Видимый элемент с атрибутом data-tour. AntD держит скрытые вкладки в DOM — берём видимый. */
export function findTourTarget(id: string): HTMLElement | null {
  const nodes = document.querySelectorAll<HTMLElement>(`[data-tour="${id}"]`);
  for (const el of nodes) if (el.getClientRects().length > 0) return el;
  return null;
}

// ponytail: опрос раз в 150 мс; MutationObserver — если опрос окажется заметен
async function waitForTarget(id: string, timeoutMs = 5000): Promise<HTMLElement | null> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const el = findTourTarget(id);
    if (el) return el;
    await new Promise(r => setTimeout(r, 150));
  }
  return null;
}

/** Подготовить шаг: переключить вкладку и дождаться цели. Цели нет — шаг покажется по центру. */
export async function prepareStep(step: TourStepDef): Promise<void> {
  if (step.clickFirst) {
    const tab = await waitForTarget(step.clickFirst);
    tab?.click();
  }
  if (step.target) await waitForTarget(step.target);
}
