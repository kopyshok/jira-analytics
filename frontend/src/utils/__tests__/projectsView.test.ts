import { describe, expect, it } from 'vitest';
import {
  datesByKey, hoursText, loadTone, loadVerdict, monthYear, pluralProjects, pluralRu,
  projectYearOptions, ratingAverage, shortDate, stageBar, statusTone, timelineScale,
} from '../projectsView';
import type { PlanTimeline } from '../../types/projects';

describe('склонения', () => {
  it('pluralRu выбирает форму по числу', () => {
    const f: [string, string, string] = ['задача', 'задачи', 'задач'];
    expect(pluralRu(1, f)).toBe('задача');
    expect(pluralRu(21, f)).toBe('задача');
    expect(pluralRu(42, f)).toBe('задачи');
    expect(pluralRu(11, f)).toBe('задач');
    expect(pluralRu(38, f)).toBe('задач');
    expect(pluralRu(0, f)).toBe('задач');
  });
  it('pluralProjects — как было в сводке портфеля', () => {
    expect(pluralProjects(1)).toBe('проект');
    expect(pluralProjects(94)).toBe('проекта');
    expect(pluralProjects(6)).toBe('проектов');
    expect(pluralProjects(112)).toBe('проектов');
  });
});

describe('числа и даты', () => {
  it('hoursText округляет и делит разряды', () => {
    expect(hoursText(1760.4).replace(/\s/g, ' ')).toBe('1 760');
    expect(hoursText(24)).toBe('24');
  });
  it('projectYearOptions — прошлый год и четыре вперёд', () => {
    expect(projectYearOptions(2026).map((o) => o.value)).toEqual([2025, 2026, 2027, 2028, 2029]);
  });
  it('shortDate и monthYear', () => {
    expect(shortDate('2026-07-01')).toBe('01.07');
    expect(shortDate('2026-12-25T00:00:00')).toBe('25.12');
    expect(shortDate(null)).toBe('');
    expect(monthYear('2026-10-05')).toBe('окт. 26');
    expect(monthYear('2026-05-01')).toBe('май 26');
    expect(monthYear(null)).toBe('—');
  });
});

describe('тона и оценки', () => {
  it('loadTone и loadVerdict — границы 70 и 110', () => {
    expect(loadTone(118)).toBe('bad');
    expect(loadTone(110)).toBe('good');
    expect(loadTone(70)).toBe('good');
    expect(loadTone(53)).toBe('warn');
    expect(loadTone(null)).toBe('neutral');
    expect(loadVerdict(76)).toBe('в норме');
    expect(loadVerdict(153)).toBe('перегруз');
    expect(loadVerdict(9)).toBe('ниже нормы');
    expect(loadVerdict(null)).toBeNull();
  });
  it('statusTone по категории статуса', () => {
    expect(statusTone('done')).toBe('good');
    expect(statusTone('indeterminate')).toBe('info');
    expect(statusTone('new')).toBe('neutral');
    expect(statusTone(null)).toBe('neutral');
  });
  it('ratingAverage — среднее по заполненным', () => {
    expect(ratingAverage({ rating_quality: 4, rating_speed: 5, rating_result: null })).toBe(4.5);
    expect(ratingAverage({ rating_quality: null, rating_speed: null, rating_result: null })).toBeNull();
  });
});

describe('stageBar', () => {
  it('до плана — доля факта', () => {
    expect(stageBar(60, 100)).toEqual({ base: 60, over: 0 });
    expect(stageBar(0, 80)).toEqual({ base: 0, over: 0 });
  });
  it('сверх плана — план плюс перерасход', () => {
    const r = stageBar(80, 70);
    expect(r.base).toBeCloseTo(87.5, 1);
    expect(r.over).toBeCloseTo(12.5, 1);
  });
  it('без плана — весь факт перерасход', () => {
    expect(stageBar(2, 0)).toEqual({ base: 0, over: 100 });
    expect(stageBar(0, 0)).toEqual({ base: 0, over: 0 });
  });
});

const TL: PlanTimeline = {
  start: '2026-09-20',
  end: '2027-01-10',
  quarter_start: '2026-10-01',
  quarter_end: '2026-12-31',
  rows: [
    { key: 'RFA-112', title: 'Онлайн-заявка', status: null, bars: [
      { phase: 'analyst', label: 'Анализ', start_date: '2026-10-01', end_date: '2026-10-17' },
      { phase: 'dev', label: 'Разработка', start_date: '2026-10-19', end_date: '2026-12-04' },
    ] },
    { key: null, title: 'Без ключа', status: null, bars: [] },
  ],
};

describe('datesByKey', () => {
  it('границы работ по полосам проекта', () => {
    expect(datesByKey(TL)).toEqual({ 'RFA-112': { start: '2026-10-01', end: '2026-12-04' } });
  });
});

describe('timelineScale', () => {
  const s = timelineScale(TL, new Date(2026, 9, 16))!;
  it('целые месяцы от сентября до января, квартал отмечен', () => {
    expect(s.months.map((m) => m.label)).toEqual(['сен', 'окт', 'ноя', 'дек', 'янв']);
    expect(s.months.map((m) => m.inQuarter)).toEqual([false, true, true, true, false]);
    const total = s.months.reduce((acc, m) => acc + m.width, 0);
    expect(total).toBeCloseTo(100, 5);
    // 30 дней сентября из 153 дней шкалы
    expect(s.months[1].left).toBeCloseTo((30 / 153) * 100, 5);
  });
  it('края квартала и «сегодня»', () => {
    expect(s.quarterLeft).toBeCloseTo(s.months[1].left, 5);
    expect(s.quarterRight).toBeCloseTo(s.months[4].left, 5);
    expect(s.todayLeft).toBeCloseTo(((30 + 15) / 153) * 100, 5);
    expect(timelineScale(TL, new Date(2025, 0, 1))!.todayLeft).toBeNull();
  });
  it('полоса — конец включительно', () => {
    const b = s.bar('2026-10-01', '2026-10-17');
    expect(b.left).toBeCloseTo((30 / 153) * 100, 5);
    expect(b.width).toBeCloseTo((17 / 153) * 100, 5);
  });
  it('нет дат — шкалы нет', () => {
    expect(timelineScale({ ...TL, start: null })).toBeNull();
  });
});
