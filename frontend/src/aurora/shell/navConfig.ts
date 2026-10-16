import { useLocation } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  FolderKanban,
  BarChart3,
  Lightbulb,
  Rocket,
  Gauge,
  Users,
  ListChecks,
  Presentation,
  Network,
  RefreshCw,
  Tags,
  MessageCircle,
  Settings,
  Code2,
  type LucideIcon as LucideIconType,
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { getHiddenSections } from '../../api/uiConfig';

/**
 * Общее меню продукта — единый источник для всех оболочек (Aurora, скины).
 * Список пунктов должен совпадать с `SECTIONS` в `VisibilityTab`.
 */

export type NavGroupId = 'overview' | 'planning' | 'data';

export interface NavItem {
  key: string;
  icon: LucideIconType;
  label: string;
  adminOnly?: boolean;
}

export interface NavGroup {
  id: NavGroupId;
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    id: 'overview',
    label: 'Обзор',
    items: [
      { key: '/', icon: LayoutDashboard, label: 'Дашборд' },
      { key: '/projects', icon: FolderKanban, label: 'Проекты' },
      { key: '/analytics', icon: BarChart3, label: 'Аналитика' },
      { key: '/analytics/work-type-report', icon: Lightbulb, label: 'Тематический отчёт' },
      { key: '/executive', icon: Rocket, label: 'Сводка для руководителя' },
      { key: '/kpi', icon: Gauge, label: 'KPI' },
      { key: '/team-desk', icon: Code2, label: 'Стол тимлида' },
    ],
  },
  {
    id: 'planning',
    label: 'Планирование',
    items: [
      { key: '/capacity', icon: Users, label: 'Ресурсы' },
      { key: '/backlog', icon: ListChecks, label: 'Целевые задачи' },
      { key: '/planning', icon: Presentation, label: 'Сценарии' },
      { key: '/resource-planning', icon: Network, label: 'Ресурс. планир.' },
    ],
  },
  {
    id: 'data',
    label: 'Данные',
    items: [
      { key: '/sync', icon: RefreshCw, label: 'Синхронизация' },
      { key: '/categories', icon: Tags, label: 'Категории задач' },
      { key: '/feedback', icon: MessageCircle, label: 'Обратная связь' },
      { key: '/settings', icon: Settings, label: 'Настройки', adminOnly: true },
    ],
  },
];

/** Служебные разделы вне меню, которые относятся к группе (для оболочек с зонами). */
const EXTRA_GROUP_PREFIXES: Record<string, NavGroupId> = {
  '/admin': 'data',
};

/** Ключ выбранного пункта меню по адресу: `/projects/*` подсвечивает «Проекты». */
export function selectedNavKey(pathname: string): string {
  return pathname.startsWith('/projects') ? '/projects' : pathname;
}

function isUnder(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

/**
 * Пункт меню и группа, к которым относится адрес: точное совпадение, иначе самый
 * длинный родительский пункт (`/resource-planning/compare` → «Ресурс. планир.»).
 * Ищет по полному меню — скрытые разделы тоже относятся к своей группе.
 */
export function navMatch(pathname: string): { group: NavGroup; item: NavItem | null } {
  const key = selectedNavKey(pathname);
  let best: { group: NavGroup; item: NavItem } | null = null;
  for (const group of NAV_GROUPS) {
    for (const item of group.items) {
      if (item.key === key) return { group, item };
      if (item.key !== '/' && isUnder(key, item.key)) {
        if (!best || item.key.length > best.item.key.length) best = { group, item };
      }
    }
  }
  if (best) return best;
  for (const [prefix, id] of Object.entries(EXTRA_GROUP_PREFIXES)) {
    if (isUnder(key, prefix)) {
      return { group: NAV_GROUPS.find((g) => g.id === id) ?? NAV_GROUPS[0], item: null };
    }
  }
  return { group: NAV_GROUPS[0], item: null };
}

/**
 * Видимое пользователю меню: без скрытых админом разделов и без админских пунктов
 * для не-админа; пустые группы убраны. Плюс ключ выбранного пункта.
 */
export function useNavSections(): { groups: NavGroup[]; selectedKey: string } {
  const location = useLocation();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const { data: hidden } = useQuery({
    queryKey: ['ui-config', 'hidden-sections'],
    queryFn: getHiddenSections,
    staleTime: 60_000,
    enabled: !!user,
  });
  const hiddenSet = new Set(hidden?.keys ?? []);

  const groups = NAV_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((it) => (!it.adminOnly || isAdmin) && !hiddenSet.has(it.key)),
  })).filter((g) => g.items.length > 0);

  return { groups, selectedKey: selectedNavKey(location.pathname) };
}
