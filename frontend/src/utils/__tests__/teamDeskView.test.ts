import { describe, expect, it } from 'vitest';
import {
  FLAG_TONE, STATUS_GROUP_TONE, accuracyLevel, cardSeverity, deskAvatarTone,
  deskInitials, deskShortName, severityBadge,
} from '../teamDeskView';
import { FLAG_ORDER, STATUS_GROUP_ORDER } from '../../api/teamDesk';
import { contrastRatio } from '../readableColor';

describe('deskInitials / deskShortName', () => {
  it('берёт первые буквы двух слов', () => {
    expect(deskInitials('Иванов Сергей')).toBe('ИС');
    expect(deskInitials('Платон')).toBe('П');
    expect(deskInitials(null)).toBe('?');
  });
  it('сокращает второе слово до буквы', () => {
    expect(deskShortName('Иванов Сергей')).toBe('Иванов С.');
    expect(deskShortName('  Петрова   Анна  ')).toBe('Петрова А.');
    expect(deskShortName('Платон')).toBe('Платон');
    expect(deskShortName(null)).toBe('Без имени');
  });
});

describe('accuracyLevel', () => {
  it.each([
    [null, null],
    [1.31, 'bad'],
    [1.3, 'good'],
    [1, 'good'],
    [0.7, 'good'],
    [0.69, 'warn'],
  ])('%s → %s', (value, level) => {
    expect(accuracyLevel(value)).toBe(level);
  });
});

describe('cardSeverity / severityBadge', () => {
  it('перерасход — сильная пометка с часами сверх оценки', () => {
    expect(cardSeverity({ over: 1, stale: 2 })).toBe(2);
    expect(severityBadge({ flag_counts: { over: 1 }, fact_hours: 71, est_hours: 64 }))
      .toEqual({ tone: 'bad', label: 'Перерасход 7 ч' });
  });
  it('перерасход без суммарного превышения — без часов', () => {
    expect(severityBadge({ flag_counts: { over: 1 }, fact_hours: 50, est_hours: 64 }))
      .toEqual({ tone: 'bad', label: 'Перерасход' });
    expect(severityBadge({ flag_counts: { over: 1 }, fact_hours: 5, est_hours: 0 }))
      .toEqual({ tone: 'bad', label: 'Перерасход' });
  });
  it('без декомпозиции важнее «зависла», обе — слабые', () => {
    expect(cardSeverity({ decomp: 1 })).toBe(1);
    expect(severityBadge({ flag_counts: { decomp: 1, stale: 3 }, fact_hours: 0, est_hours: 10 }))
      .toEqual({ tone: 'warn', label: 'Без декомпозиции' });
    expect(severityBadge({ flag_counts: { stale: 3 }, fact_hours: 0, est_hours: 10 }))
      .toEqual({ tone: 'warn', label: 'Зависла' });
  });
  it('прочие признаки пометки не дают', () => {
    expect(cardSeverity({ noest: 4, nospent: 1 })).toBe(0);
    expect(severityBadge({ flag_counts: { noest: 4 }, fact_hours: 0, est_hours: 0 })).toBeNull();
  });
});

describe('тоны и аватары', () => {
  it('у каждого признака и группы статусов есть тон', () => {
    FLAG_ORDER.forEach((flag) => expect(FLAG_TONE[flag]).toBeTruthy());
    STATUS_GROUP_ORDER.forEach((group) => expect(STATUS_GROUP_TONE[group]).toBeTruthy());
  });
  it('аватар одного человека всегда одного цвета и читается', () => {
    const a = deskAvatarTone('Иванов Сергей');
    expect(deskAvatarTone('Иванов Сергей')).toEqual(a);
    ['Иванов Сергей', 'Петрова Анна', 'Ковалёв Дмитрий', 'Смирнова Ольга', null].forEach((name) => {
      const tone = deskAvatarTone(name);
      expect(contrastRatio(tone.fg, tone.bg)).toBeGreaterThanOrEqual(4.5);
    });
  });
});
