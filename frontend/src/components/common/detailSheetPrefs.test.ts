import { describe, expect, it } from 'vitest';
import { parsePrefs } from './detailSheetPrefs';

describe('parsePrefs', () => {
  it('пусто и мусор — лист снизу по умолчанию', () => {
    expect(parsePrefs(null)).toEqual({ placement: 'bottom', bottom: 0.55, right: 0.5 });
    expect(parsePrefs('{oops')).toEqual({ placement: 'bottom', bottom: 0.55, right: 0.5 });
    expect(parsePrefs('42')).toEqual({ placement: 'bottom', bottom: 0.55, right: 0.5 });
  });

  it('сохранённое место и размер, выход за пределы — к границе', () => {
    expect(parsePrefs('{"placement":"right","bottom":0.1,"right":0.95}')).toEqual({
      placement: 'right',
      bottom: 0.3,
      right: 0.8,
    });
  });
});
