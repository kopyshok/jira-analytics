import { roundHours, type DeskDeveloper, type FlagCode, type StatusGroup } from '../api/teamDesk';

/**
 * Чистые правила отображения «Рабочего стола тимлида», общие для раскладки
 * Aurora и раскладок скинов: тяжесть замечаний, уровень точности оценок,
 * тон пилюль признаков и статусов, инициалы и короткие имена.
 */

/** Тон мягкой пилюли: светлая подложка + тёмный текст того же оттенка. */
export type DeskTone = 'bad' | 'warn' | 'info' | 'neutral' | 'good' | 'violet';

/** Инициалы для кружка-аватара: первые буквы двух первых слов имени. */
export function deskInitials(name: string | null): string {
  if (!name) return '?';
  const parts = name.split(' ');
  return (parts[0][0] + (parts[1]?.[0] ?? '')).toUpperCase();
}

/** «Иванов Сергей» → «Иванов С.»: подпись строки в узкой колонке. */
export function deskShortName(name: string | null): string {
  if (!name) return 'Без имени';
  const parts = name.trim().split(/\s+/);
  return parts.length > 1 ? `${parts[0]} ${parts[1][0]}.` : parts[0];
}

/**
 * Точность оценок: выше 1.3 — оценки сильно занижены, ниже 0.7 — завышены,
 * между — норма. Нет точности — нет уровня.
 */
export function accuracyLevel(value: number | null): 'bad' | 'warn' | 'good' | null {
  if (value == null) return null;
  if (value > 1.3) return 'bad';
  if (value < 0.7) return 'warn';
  return 'good';
}

/** Тяжесть замечаний разработчика: перерасход — сильная, без декомпозиции или зависла — слабая. */
export function cardSeverity(flagCounts: Partial<Record<FlagCode, number>>): 0 | 1 | 2 {
  if (flagCounts.over) return 2;
  if (flagCounts.decomp || flagCounts.stale) return 1;
  return 0;
}

/**
 * Пометка проблемы на плитке разработчика — та же тяжесть, словами: при
 * перерасходе — сколько часов сверх оценки по всем его задачам.
 */
export function severityBadge(
  dev: Pick<DeskDeveloper, 'flag_counts' | 'fact_hours' | 'est_hours'>,
): { tone: 'bad' | 'warn'; label: string } | null {
  const severity = cardSeverity(dev.flag_counts);
  if (severity === 2) {
    const over = dev.est_hours > 0 ? roundHours(dev.fact_hours - dev.est_hours) : 0;
    return { tone: 'bad', label: over > 0 ? `Перерасход ${Math.round(over)} ч` : 'Перерасход' };
  }
  if (severity === 1) {
    return { tone: 'warn', label: dev.flag_counts.decomp ? 'Без декомпозиции' : 'Зависла' };
  }
  return null;
}

/** Тон признака: перерасход и недооценённые подзадачи — сильные, остальное — предупреждения. */
export const FLAG_TONE: Record<FlagCode, DeskTone> = {
  over: 'bad',
  childgap: 'bad',
  under: 'warn',
  decomp: 'warn',
  noest: 'warn',
  idlespent: 'warn',
  stale: 'warn',
  orphan: 'violet',
  alien: 'info',
  nospent: 'neutral',
};

/** Тон группы статусов: у разработчика — синий, ждёт не его — охра, не начата — серый. */
export const STATUS_GROUP_TONE: Record<StatusGroup, DeskTone> = {
  dev: 'info',
  waiting: 'warn',
  todo: 'neutral',
  done: 'good',
  unassigned: 'violet',
};

/** Мягкие тёплые подложки аватаров: пыльно-голубой, шалфей, глиняный, песочный. */
const AVATAR_TONES: { bg: string; fg: string }[] = [
  { bg: '#D9E2EC', fg: '#34506E' },
  { bg: '#DCE6D6', fg: '#3E5A38' },
  { bg: '#EBD6CC', fg: '#7A3E27' },
  { bg: '#EADFC8', fg: '#6B4E1E' },
];

/** Подложка аватара по имени: один человек — всегда один цвет на всех блоках. */
export function deskAvatarTone(name: string | null): { bg: string; fg: string } {
  const key = name ?? '';
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  return AVATAR_TONES[hash % AVATAR_TONES.length];
}
