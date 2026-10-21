import type { TourStepDef } from './tours';

/** Видимый элемент с атрибутом data-tour. AntD держит скрытые вкладки в DOM — берём видимый. */
export function findTourTarget(id: string): HTMLElement | null {
  const nodes = document.querySelectorAll<HTMLElement>(`[data-tour="${id}"]`);
  for (const el of nodes) if (el.getClientRects().length > 0) return el;
  return null;
}

/** Что показать на шаге: цель, заголовок и текст. */
export type TourStepView = Pick<TourStepDef, 'target' | 'title' | 'description'>;

/**
 * Вариант шага: основной, если его цель на странице; иначе запасной
 * (`otherwise`), если на странице его цель; иначе основной — окно по центру.
 */
export function resolveTourStep(step: TourStepDef, isPresent: (id: string) => boolean): TourStepView {
  const main = { target: step.target, title: step.title, description: step.description };
  if (step.target && isPresent(step.target)) return main;
  if (step.otherwise && isPresent(step.otherwise.target)) return step.otherwise;
  return main;
}

// ponytail: опрос раз в 150 мс; MutationObserver — если опрос окажется заметен
async function waitForTarget(ids: string[], timeoutMs = 5000): Promise<HTMLElement | null> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    for (const id of ids) {
      const el = findTourTarget(id);
      if (el) return el;
    }
    await new Promise(r => setTimeout(r, 150));
  }
  return null;
}

/**
 * Подготовить шаг: переключить вкладку, дождаться цели (основной или запасной) и
 * вернуть вариант шага для показа. Цели нет — шаг покажется по центру.
 * timeoutMs — сколько ждать цель (шаг 0 после навигации ждёт дольше, чем переключение
 * между уже отрисованными шагами). isCurrent — шаг ещё актуален (экскурсию не закрыли
 * и не обогнали более новым переключением), проверяется перед кликом: цель могла
 * появиться, когда пользователь уже ушёл дальше.
 */
export async function prepareStep(step: TourStepDef, timeoutMs: number, isCurrent: () => boolean): Promise<TourStepView> {
  if (step.clickFirst) {
    const tab = await waitForTarget([step.clickFirst], timeoutMs);
    if (tab && isCurrent()) tab.click();
  }
  const ids = [step.target, step.otherwise?.target].filter((id): id is string => !!id);
  if (ids.length > 0) await waitForTarget(ids, timeoutMs);
  return resolveTourStep(step, id => !!findTourTarget(id));
}
