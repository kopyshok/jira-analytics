/**
 * Последовательное сохранение «последнего значения»: пока идёт запрос, новые значения
 * не отправляются, а запоминаются; после ответа уходит только самое свежее.
 * onIdle(ok) — очередь опустела; ok = последний отправленный запрос прошёл.
 */
export function createLatestSaver<T>(
  save: (value: T) => Promise<unknown>,
  onIdle?: (ok: boolean) => void,
): (value: T) => void {
  let running = false;
  let hasPending = false;
  let pending: T;

  const run = async (value: T) => {
    running = true;
    let ok = true;
    try {
      await save(value);
    } catch {
      ok = false;
    }
    if (hasPending) {
      hasPending = false;
      void run(pending);
      return;
    }
    running = false;
    onIdle?.(ok);
  };

  return (value: T) => {
    if (running) {
      pending = value;
      hasPending = true;
    } else {
      void run(value);
    }
  };
}
