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
 * Единое меню приложения — общее для всех оболочек (Aurora и обложки).
 * Список пунктов должен совпадать с `SECTIONS` в `VisibilityTab`.
 */
export interface NavItem {
  key: string;
  icon: LucideIconType;
  label: string;
  adminOnly?: boolean;
}
export interface NavGroup {
  id: 'overview' | 'planning' | 'data';
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

/** Группа, к которой относится адрес: точный пункт или самый длинный префикс. */
export function findGroupForPath(groups: NavGroup[], pathname: string): NavGroup | undefined {
  let best: { group: NavGroup; len: number } | undefined;
  for (const group of groups) {
    for (const { key } of group.items) {
      const hit = key === '/'
        ? pathname === '/'
        : pathname === key || pathname.startsWith(`${key}/`);
      if (hit && (!best || key.length > best.len)) best = { group, len: key.length };
    }
  }
  return best?.group;
}

/**
 * Видимые группы меню (скрытые разделы и admin-only вырезаны, пустые группы
 * убраны) + ключ выбранного пункта (`/projects*` → «Проекты»).
 */
export function useNavSections(): { groups: NavGroup[]; selectedKey: string; pathname: string } {
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

  const groups = NAV_GROUPS
    .map((g) => ({
      ...g,
      items: g.items.filter((it) => (!it.adminOnly || isAdmin) && !hiddenSet.has(it.key)),
    }))
    .filter((g) => g.items.length > 0);

  const selectedKey = location.pathname.startsWith('/projects')
    ? '/projects'
    : location.pathname;

  return { groups, selectedKey, pathname: location.pathname };
}
