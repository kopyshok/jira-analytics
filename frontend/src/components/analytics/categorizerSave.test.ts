import { describe, expect, it } from 'vitest';
import { saveCategorization, saveFailureNotice } from './categorizerSave';

const ok = () => Promise.resolve();
const fail = (msg: string) => () => Promise.reject(new Error(msg));

describe('карточка задачи: сохранение категории', () => {
  it('удачное сохранение — категория, затем «Учитывать в анализе»', async () => {
    const order: string[] = [];
    const res = await saveCategorization(
      async () => { order.push('category'); },
      async () => { order.push('include'); },
    );
    expect(res).toEqual({ ok: true });
    expect(order).toEqual(['category', 'include']);
  });

  it('сбой категории не роняет страницу: итог с причиной, дальше не идём', async () => {
    let includeCalled = false;
    const res = await saveCategorization(fail('Задача не найдена'), async () => { includeCalled = true; });
    expect(res).toEqual({ ok: false, categorySaved: false, reason: 'Задача не найдена' });
    expect(includeCalled).toBe(false);
  });

  it('категория сохранилась, а галочка — нет', async () => {
    const res = await saveCategorization(ok, fail('Internal Server Error'));
    expect(res).toEqual({ ok: false, categorySaved: true, reason: 'Internal Server Error' });
  });

  it('обрыв связи — понятная причина', async () => {
    const res = await saveCategorization(() => Promise.reject(new TypeError('Failed to fetch')), ok);
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.reason).toBe('нет связи с сервером');
  });
});

describe('карточка задачи: текст о сбое', () => {
  it('категория не сохранена — поле вернулось к прежнему значению', () => {
    const n = saveFailureNotice({ categorySaved: false, reason: 'Задача не найдена' });
    expect(n.title).toBe('Не удалось сохранить категорию');
    expect(n.description).toContain('Задача не найдена');
    expect(n.description).toContain('прежнее значение');
  });

  it('категория сохранена, галочка нет — предлагаем повторить', () => {
    const n = saveFailureNotice({ categorySaved: true, reason: 'Internal Server Error' });
    expect(n.title).toContain('Категория сохранена');
    expect(n.description).toContain('ещё раз');
  });
});
