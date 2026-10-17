/**
 * Чистые помощники раздела «Проекты»: склонения, тона пилюль, полосы
 * «факт / план» и шкала таймлайна портфеля. Общие для раскладки Aurora и
 * раскладок скинов, поэтому без React и без цветов — только числа и слова.
 */
import type { PlanTimeline, ProjectListItem } from '../types/projects';

/** Выше этого процента загрузка считается перегрузом — та же граница, что в кольцах и Capacity. */
export const OVERLOAD_PCT = 110;
/** С этого процента загрузка «в норме». */
export const NORMAL_PCT = 70;

/** Русское склонение под число: 1 задача, 3 задачи, 5 задач. */
export function pluralRu(n: number, forms: [string, string, string]): string {
  const abs = Math.abs(Math.trunc(n));
  if (abs % 100 >= 11 && abs % 100 <= 14) return forms[2];
  const last = abs % 10;
  if (last === 1) return forms[0];
  if (last >= 2 && last <= 4) return forms[1];
  return forms[2];
}

/** Склонение слова «проект» под число: 1 проект, 3 проекта, 5 проектов. */
export function pluralProjects(n: number): string {
  return pluralRu(n, ['проект', 'проекта', 'проектов']);
}

/** Часы целым числом с разрядами: 1760 → «1 760». */
export function hoursText(h: number): string {
  return Math.round(h).toLocaleString('ru-RU');
}

/** Годы в списке «Год»: прошлый, текущий и три следующих. */
export function projectYearOptions(currentYear: number): Array<{ value: number; label: string }> {
  return Array.from({ length: 5 }, (_, i) => {
    const y = currentYear - 1 + i;
    return { value: y, label: String(y) };
  });
}

export type Tone = 'good' | 'warn' | 'bad' | 'info' | 'neutral';

/** Тон пилюли загрузки: перегруз — красный, норма — зелёный, ниже нормы — охра. */
export function loadTone(pct: number | null): Tone {
  if (pct === null) return 'neutral';
  if (pct > OVERLOAD_PCT) return 'bad';
  if (pct >= NORMAL_PCT) return 'good';
  return 'warn';
}

/** Словесная оценка загрузки портфеля рядом с процентом. */
export function loadVerdict(pct: number | null): string | null {
  if (pct === null) return null;
  if (pct > OVERLOAD_PCT) return 'перегруз';
  if (pct >= NORMAL_PCT) return 'в норме';
  return 'ниже нормы';
}

/** Тон статуса по его категории в Jira: готово / в работе / новый. */
export function statusTone(category: string | null | undefined): Tone {
  if (category === 'done') return 'good';
  if (category === 'indeterminate') return 'info';
  return 'neutral';
}

/**
 * Мини-полоса «факт / план»: доля плана и доля перерасхода. До 100 % полоса
 * заполнена на процент; сверх плана вся полоса — факт, из неё план занимает
 * plan / fact, остаток красится перерасходом; часы без плана — весь перерасход.
 */
export function stageBar(fact: number, plan: number): { base: number; over: number } {
  // Часы без плана — целиком перерасход.
  if (plan <= 0) return fact > 0 ? { base: 0, over: 100 } : { base: 0, over: 0 };
  if (fact <= plan) return { base: (Math.max(0, fact) / plan) * 100, over: 0 };
  const base = (plan / fact) * 100;
  return { base, over: 100 - base };
}

/** Средняя оценка заказчика по заполненным полям; null — оценок нет. */
export function ratingAverage(
  item: Pick<ProjectListItem, 'rating_quality' | 'rating_speed' | 'rating_result'>,
): number | null {
  const vals = [item.rating_quality, item.rating_speed, item.rating_result]
    .filter((v): v is number => v != null);
  if (vals.length === 0) return null;
  return vals.reduce((s, v) => s + v, 0) / vals.length;
}

/** '2026-07-01' → '01.07'. Пустая строка, если даты нет. */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const [, m, d] = iso.split('-');
  return m && d ? `${d.slice(0, 2)}.${m}` : '';
}

const MONTHS_SHORT = ['янв.', 'фев.', 'мар.', 'апр.', 'май', 'июн.', 'июл.', 'авг.', 'сен.', 'окт.', 'ноя.', 'дек.'];
const MONTHS_AXIS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

/** '2026-10-05' → 'окт. 26' — период проекта в карточке списка. */
export function monthYear(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [y, m] = iso.split('-').map(Number);
  if (!y || !m) return '—';
  return `${MONTHS_SHORT[m - 1]} ${String(y).slice(-2)}`;
}

/** Границы работ по каждому проекту — из полос таймлайна, отдельного запроса не нужно. */
export function datesByKey(timeline: PlanTimeline): Record<string, { start: string; end: string }> {
  const out: Record<string, { start: string; end: string }> = {};
  timeline.rows.forEach((row) => {
    if (!row.key || row.bars.length === 0) return;
    const starts = row.bars.map((b) => b.start_date).sort();
    const ends = row.bars.map((b) => b.end_date).sort();
    out[row.key] = { start: starts[0], end: ends[ends.length - 1] };
  });
  return out;
}

/** Дата ISO как местная полночь — шкала считается в днях, без сдвига часовых поясов. */
function localDay(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

const DAY = 24 * 60 * 60 * 1000;

export interface TimelineScale {
  /** Месяцы шкалы: подпись, левый край и ширина в процентах, внутри ли квартала. */
  months: Array<{ label: string; left: number; width: number; inQuarter: boolean }>;
  /** Левый край квартала и правый (день после последнего) в процентах. */
  quarterLeft: number;
  quarterRight: number;
  /** Вертикаль «сегодня» в процентах; null — сегодня вне шкалы. */
  todayLeft: number | null;
  /** Полоса фазы: левый край и ширина в процентах, конец включительно. */
  bar: (start: string, end: string) => { left: number; width: number };
}

/**
 * Шкала таймлайна портфеля: целые месяцы от первого до последнего, края
 * квартала и «сегодня». Ширины месяцев — по числу дней, чтобы полосы и
 * подписи совпадали.
 */
export function timelineScale(timeline: PlanTimeline, now: Date = new Date()): TimelineScale | null {
  if (!timeline.start || !timeline.end) return null;
  const first = localDay(timeline.start);
  const last = localDay(timeline.end);
  const s0 = new Date(first.getFullYear(), first.getMonth(), 1).getTime();
  const s1 = new Date(last.getFullYear(), last.getMonth() + 1, 1).getTime();
  const span = s1 - s0 || 1;
  const pos = (t: number) => Math.max(0, Math.min(100, ((t - s0) / span) * 100));

  const q0 = localDay(timeline.quarter_start).getTime();
  const q1 = localDay(timeline.quarter_end).getTime() + DAY;

  const months: TimelineScale['months'] = [];
  const cur = new Date(s0);
  while (cur.getTime() < s1) {
    const next = new Date(cur.getFullYear(), cur.getMonth() + 1, 1);
    const left = pos(cur.getTime());
    months.push({
      label: MONTHS_AXIS[cur.getMonth()],
      left,
      width: pos(next.getTime()) - left,
      inQuarter: cur.getTime() >= q0 && cur.getTime() < q1,
    });
    cur.setTime(next.getTime());
  }

  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return {
    months,
    quarterLeft: pos(q0),
    quarterRight: pos(q1),
    todayLeft: today >= s0 && today < s1 ? pos(today) : null,
    bar: (start, end) => {
      const left = pos(localDay(start).getTime());
      const right = pos(localDay(end).getTime() + DAY);
      return { left, width: Math.max(0.6, right - left) };
    },
  };
}
