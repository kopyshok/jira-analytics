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
  type LucideIcon,
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { getHiddenSections } from '../../api/uiConfig';

export interface NavItem {
  key: string;
  icon: LucideIcon;
  label: string;
  adminOnly?: boolean;
}
export interface NavGroup {
  label: string;
  items: NavItem[];
}

/** Главное меню — одно на все оболочки. Состав должен совпадать с `SECTIONS` в VisibilityTab. */
export const NAV_GROUPS: NavGroup[] = [
  {
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
    label: 'Планирование',
    items: [
      { key: '/capacity', icon: Users, label: 'Ресурсы' },
      { key: '/backlog', icon: ListChecks, label: 'Целевые задачи' },
      { key: '/planning', icon: Presentation, label: 'Сценарии' },
      { key: '/resource-planning', icon: Network, label: 'Ресурс. планир.' },
    ],
  },
  {
    label: 'Данные',
    items: [
      { key: '/sync', icon: RefreshCw, label: 'Синхронизация' },
      { key: '/categories', icon: Tags, label: 'Категории задач' },
      { key: '/feedback', icon: MessageCircle, label: 'Обратная связь' },
      { key: '/settings', icon: Settings, label: 'Настройки', adminOnly: true },
    ],
  },
];

/**
 * Видимые группы меню (скрытые админом разделы и «Настройки» для не-админа убраны)
 * и ключ активного пункта: все `/projects*` подсвечивают «Проекты».
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

  const groups = NAV_GROUPS
    .map((g) => ({
      label: g.label,
      items: g.items.filter((it) => (!it.adminOnly || isAdmin) && !hiddenSet.has(it.key)),
    }))
    .filter((g) => g.items.length > 0);

  const selectedKey = location.pathname.startsWith('/projects')
    ? '/projects'
    : location.pathname;

  return { groups, selectedKey };
}
