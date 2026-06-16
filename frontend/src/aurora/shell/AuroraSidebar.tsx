import { useNavigate, useLocation } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  FolderKanban,
  BarChart3,
  Lightbulb,
  Rocket,
  Users,
  ListChecks,
  Presentation,
  Network,
  RefreshCw,
  Tags,
  MessageCircle,
  Settings,
  type LucideIcon as LucideIconType,
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { getHiddenSections } from '../../api/uiConfig';

interface NavItem {
  key: string;
  icon: LucideIconType;
  label: string;
}
interface NavGroup {
  label: string;
  items: NavItem[];
}

export function AuroraSidebar() {
  const navigate = useNavigate();
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
  const isHidden = (k: string) => hiddenSet.has(k);

  const groups: NavGroup[] = [
    {
      label: 'Обзор',
      items: [
        { key: '/', icon: LayoutDashboard, label: 'Дашборд' },
        { key: '/projects', icon: FolderKanban, label: 'Проекты' },
        { key: '/analytics', icon: BarChart3, label: 'Аналитика' },
        { key: '/analytics/work-type-report', icon: Lightbulb, label: 'Тематический отчёт' },
        { key: '/executive', icon: Rocket, label: 'Сводка для руководителя' },
      ].filter((it) => !isHidden(it.key)),
    },
    {
      label: 'Планирование',
      items: [
        { key: '/capacity', icon: Users, label: 'Ресурсы' },
        { key: '/backlog', icon: ListChecks, label: 'Целевые задачи' },
        { key: '/planning', icon: Presentation, label: 'Сценарии' },
        { key: '/resource-planning', icon: Network, label: 'Ресурс. планир.' },
      ].filter((it) => !isHidden(it.key)),
    },
    {
      label: 'Данные',
      items: [
        { key: '/sync', icon: RefreshCw, label: 'Синхронизация' },
        { key: '/categories', icon: Tags, label: 'Категории задач' },
        { key: '/feedback', icon: MessageCircle, label: 'Обратная связь' },
        ...(isAdmin ? [{ key: '/settings', icon: Settings, label: 'Настройки' }] : []),
      ].filter((it) => !isHidden(it.key)),
    },
  ].filter((g) => g.items.length > 0);

  const selectedKey = location.pathname.startsWith('/projects')
    ? '/projects'
    : location.pathname;

  return (
    <div className="glass side">
      <div className="side-logo">
        <svg width="30" height="30" viewBox="0 0 32 32" fill="none">
          <circle cx="16" cy="16" r="13" stroke="var(--accent-1)" strokeWidth="1.5" opacity="0.4" />
          <path d="M5 16a11 11 0 0 1 22 0" stroke="var(--accent-1)" strokeWidth="2.4" strokeLinecap="round" />
          <circle cx="16" cy="5" r="2.6" fill="var(--accent-1)" />
          <circle cx="16" cy="16" r="2.2" fill="var(--accent-2)" />
        </svg>
        <div style={{ lineHeight: 1.1 }}>
          <div className="serif" style={{ fontSize: 17, fontWeight: 600, letterSpacing: '-0.01em' }}>
            Jira
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 6,
              marginTop: 1,
            }}
          >
            <span
              style={{
                fontSize: 9.5,
                textTransform: 'uppercase',
                letterSpacing: '0.18em',
                color: 'var(--accent-1)',
                fontWeight: 600,
              }}
            >
              Analytics
            </span>
            <span
              title={`Версия ${__APP_VERSION__}`}
              style={{
                fontSize: 9,
                color: 'var(--text-muted)',
                fontWeight: 500,
                letterSpacing: '0.04em',
              }}
            >
              v{__APP_VERSION__}
            </span>
          </div>
        </div>
      </div>
      <div className="scroll-y" style={{ flex: 1, margin: '0 -4px', padding: '0 4px' }}>
        {groups.map((g) => (
          <div key={g.label}>
            <div className="side-group">{g.label}</div>
            {g.items.map(({ key, icon: Icon, label }) => (
              <button
                key={key}
                className={`side-item${selectedKey === key ? ' active' : ''}`}
                onClick={() => navigate(key)}
              >
                <span className="side-ico" style={{ display: 'inline-flex' }}>
                  <Icon size={17} strokeWidth={1.8} />
                </span>
                <span
                  style={{
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {label}
                </span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
