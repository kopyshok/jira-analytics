/**
 * Сохранение категории в карточке задачи (Аналитика). Сбой сервера или связи
 * не должен превращаться в ошибку страницы: итог возвращается значением, а
 * карточка показывает сообщение и возвращает поле к сохранённому значению.
 */

export type SaveOutcome =
  | { ok: true }
  | { ok: false; categorySaved: boolean; reason: string };

/** Понятная причина сбоя: текст сервера или «нет связи». */
export function failureReason(e: unknown): string {
  if (e instanceof TypeError) return 'нет связи с сервером';
  const msg = e instanceof Error ? e.message : '';
  return msg || 'неизвестная ошибка';
}

/** Сначала категория, затем «Учитывать в анализе»; на сбое дальше не идём. */
export async function saveCategorization(
  saveCategory: () => Promise<unknown>,
  saveInclude: () => Promise<unknown>,
): Promise<SaveOutcome> {
  let categorySaved = false;
  try {
    await saveCategory();
    categorySaved = true;
    await saveInclude();
    return { ok: true };
  } catch (e) {
    return { ok: false, categorySaved, reason: failureReason(e) };
  }
}

export function saveFailureNotice(outcome: { categorySaved: boolean; reason: string }) {
  return outcome.categorySaved
    ? {
      title: 'Категория сохранена, а «Учитывать в анализе» — нет',
      description: `Причина: ${outcome.reason}. Нажмите «Сохранить» ещё раз.`,
    }
    : {
      title: 'Не удалось сохранить категорию',
      description: `Причина: ${outcome.reason}. В поле — прежнее значение.`,
    };
}
