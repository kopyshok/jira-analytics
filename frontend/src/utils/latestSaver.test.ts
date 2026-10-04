import { describe, expect, it } from 'vitest';
import { createLatestSaver } from './latestSaver';
import { stepPriority, canStepPriority, parsePriorityInput } from './priorityStep';

const deferred = () => {
  let resolve!: () => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<void>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};
const tick = () => new Promise((r) => setTimeout(r, 0));

describe('createLatestSaver', () => {
  it('не шлёт параллельно; быстрые значения схлопываются до последнего', async () => {
    const calls: number[] = [];
    const gates: ReturnType<typeof deferred>[] = [];
    const idle: boolean[] = [];
    const push = createLatestSaver<number>(
      (v) => {
        calls.push(v);
        const d = deferred();
        gates.push(d);
        return d.promise;
      },
      (ok) => idle.push(ok),
    );
    push(1);
    push(2);
    push(3);
    expect(calls).toEqual([1]);
    gates[0].resolve();
    await tick();
    expect(calls).toEqual([1, 3]);
    gates[1].resolve();
    await tick();
    expect(idle).toEqual([true]);
    push(4);
    expect(calls).toEqual([1, 3, 4]);
  });

  it('ошибка последнего сохранения сообщается как неуспех, очередь живёт дальше', async () => {
    const idle: boolean[] = [];
    let n = 0;
    const push = createLatestSaver<number>(
      () => (++n === 1 ? Promise.reject(new Error('x')) : Promise.resolve()),
      (ok) => idle.push(ok),
    );
    push(1);
    await tick();
    expect(idle).toEqual([false]);
    push(2);
    await tick();
    expect(idle).toEqual([false, true]);
  });
});

describe('priorityStep', () => {
  it('▲ +1, пустое → 1, потолок 10', () => {
    expect(stepPriority(null, 1)).toBe(1);
    expect(stepPriority(5, 1)).toBe(6);
    expect(stepPriority(10, 1)).toBe(10);
  });
  it('▼ −1, пустое остаётся пустым, пол 1', () => {
    expect(stepPriority(null, -1)).toBeNull();
    expect(stepPriority(5, -1)).toBe(4);
    expect(stepPriority(1, -1)).toBe(1);
  });
  it('ручной ввод: пустое — прежнее значение, число — в пределах 1..10', () => {
    expect(parsePriorityInput('', 5)).toBe(5);
    expect(parsePriorityInput('', null)).toBeNull();
    expect(parsePriorityInput('abc', 4)).toBe(4);
    expect(parsePriorityInput('0', 4)).toBe(1);
    expect(parsePriorityInput('99', 4)).toBe(10);
    expect(parsePriorityInput('7', 4)).toBe(7);
  });
  it('доступность кнопок', () => {
    expect(canStepPriority(null, 1)).toBe(true);
    expect(canStepPriority(null, -1)).toBe(false);
    expect(canStepPriority(10, 1)).toBe(false);
    expect(canStepPriority(1, -1)).toBe(false);
    expect(canStepPriority(5, 1)).toBe(true);
    expect(canStepPriority(5, -1)).toBe(true);
  });
});
