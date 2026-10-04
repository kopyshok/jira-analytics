import { describe, expect, it } from 'vitest';
import { filenameFromContentDisposition } from './contentDisposition';

describe('filenameFromContentDisposition', () => {
  it('предпочитает filename* и раскодирует UTF-8', () => {
    const h = `attachment; filename="_____.xlsx"; filename*=UTF-8''%D0%9F%D0%BB%D0%B0%D0%BD%20Q4.xlsx`;
    expect(filenameFromContentDisposition(h)).toBe('План Q4.xlsx');
  });

  it('без filename* берёт filename', () => {
    expect(filenameFromContentDisposition('attachment; filename="report.xlsx"')).toBe('report.xlsx');
    expect(filenameFromContentDisposition('attachment; filename=report.xlsx')).toBe('report.xlsx');
  });

  it('битое кодирование в filename* — падаем на filename', () => {
    const h = `attachment; filename="a.xlsx"; filename*=UTF-8''%E0%A4%A`;
    expect(filenameFromContentDisposition(h)).toBe('a.xlsx');
  });

  it('нет заголовка или имени — null', () => {
    expect(filenameFromContentDisposition(null)).toBeNull();
    expect(filenameFromContentDisposition('attachment')).toBeNull();
  });
});
