import { useCallback, type ReactNode } from 'react';
import { Outlet, useNavigate } from 'react-router';
import {
  BriefcaseBusiness,
  CalendarDays,
  ChartNoAxesColumn,
  FileText,
  Flag,
  Folder,
  GitBranch,
  LayoutGrid,
  LogOut,
  MessageSquare,
  RefreshCw,
  Settings,
  SquareCheck,
  Tag,
  Target,
  Users,
  type LucideIcon,
} from 'lucide-react';
import { useAuth } from '../../../hooks/useAuth';
import { useEventStream } from '../../../hooks/useEventStream';
import { useThemeSync } from '../../../hooks/useTheme';
import { HelpProvider } from '../../../contexts/HelpContext';
import { usePageView } from '../../../lib/usage/usePageView';
import { useHeartbeat } from '../../../lib/usage/useHeartbeat';
import { trackAction } from '../../../lib/usage/track';
import { useNavSections } from '../../../aurora/shell/navConfig';
import FeedbackButton from '../../../components/feedback/FeedbackButton';
import WhatsNewGate from '../../../components/release-notes/WhatsNewGate';
import GlobalTeamFilterButton from '../../../components/Layout/GlobalTeamFilterButton';
import GlobalPeriodPicker from '../../../components/shared/GlobalPeriodPicker';
import GlobalHelpButton from '../../../components/Layout/GlobalHelpButton';
import SyncIndicator from '../../../components/Layout/SyncIndicator';
import ThemeSelect from '../../../components/Layout/ThemeSelect';
import OnboardingButton from '../../../onboarding/OnboardingButton';
import './WarmShell.css';

/** Значки пунктов меню как в макетах C-*: тот же состав меню (navConfig), свой рисунок. */
const ICONS: Record<string, LucideIcon> = {
  '/': LayoutGrid,
  '/projects': Folder,
  '/analytics': ChartNoAxesColumn,
  '/analytics/work-type-report': FileText,
  '/executive': BriefcaseBusiness,
  '/kpi': Target,
  '/team-desk': SquareCheck,
  '/capacity': Users,
  '/backlog': Flag,
  '/planning': GitBranch,
  '/resource-planning': CalendarDays,
  '/sync': RefreshCw,
  '/categories': Tag,
  '/feedback': MessageSquare,
  '/settings': Settings,
};

function initials(name: string): string {
  return name.split(' ').map((w) => w[0] || '').join('').toUpperCase().slice(0, 2);
}

function UsageTracker(): ReactNode {
  usePageView();
  useHeartbeat();
  return null;
}

function WarmSidebar() {
  const navigate = useNavigate();
  const { groups, selectedKey } = useNavSections();
  return (
    <nav className="wm-side" aria-label="Главное меню">
      <div className="wm-logo">
        <span className="wm-logo-mark" aria-hidden>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M6 17.5V9.5M12 17.5V6.5M18 17.5v-5" />
            <path d="M4.5 20h15" />
          </svg>
        </span>
        <span className="wm-logo-text">
          <span className="wm-logo-name">Jira Analytics</span>
          <span className="wm-logo-ver" title={`Версия ${__APP_VERSION__}`}>v{__APP_VERSION__}</span>
        </span>
      </div>
      <div className="wm-nav">
        {groups.map((g) => (
          <div key={g.label} className="wm-nav-group">
            <div className="wm-group">{g.label}</div>
            {g.items.map(({ key, icon, label }) => {
              const Icon = ICONS[key] ?? icon;
              const active = selectedKey === key;
              return (
                <button
                  key={key}
                  type="button"
                  className={`wm-item${active ? ' is-active' : ''}`}
                  aria-current={active ? 'page' : undefined}
                  title={label}
                  onClick={() => navigate(key)}
                >
                  <Icon size={18} strokeWidth={1.5} aria-hidden />
                  <span className="wm-item-label">{label}</span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </nav>
  );
}

function WarmTopbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const handleLogout = useCallback(async () => {
    await logout();
    trackAction('logout');
    navigate('/login', { replace: true });
  }, [logout, navigate]);

  return (
    <header className="wm-topbar">
      <div className="wm-caption">Анализ Jira · Планирование квартала</div>
      <div className="wm-controls">
        <SyncIndicator />
        {user && (
          <>
            <span data-tour="header-team" className="wm-slot"><GlobalTeamFilterButton /></span>
            <span data-tour="header-period" className="wm-slot"><GlobalPeriodPicker /></span>
            <OnboardingButton labeled />
            <span data-tour="header-help" className="wm-slot"><GlobalHelpButton /></span>
            <ThemeSelect variant="icon" />
            <span className="wm-user">
              <span className="wm-user-avatar" aria-hidden>{initials(user.display_name)}</span>
              <span className="wm-user-name">{user.display_name}</span>
              <button type="button" className="wm-user-logout" aria-label="Выйти" title="Выйти" onClick={handleLogout}>
                <LogOut size={16} strokeWidth={1.5} aria-hidden />
              </button>
            </span>
          </>
        )}
      </div>
    </header>
  );
}

/**
 * Оболочка скина «Тёплая» (макеты C-*): меню на фоне страницы со значками,
 * подписи групп обычным регистром, монограмма в скруглённом квадрате акцента,
 * активный пункт — бледно-зелёная пилюля; сверху — подпись сервиса и
 * элементы-пилюли. Обязанности те же, что у AuroraShell: поток событий,
 * синхронизация темы, справка, обратная связь, учёт посещений, «Что нового».
 * Классы app-shell / app-main / scroll-y — общие крючки раскладок страниц.
 */
export default function WarmShell() {
  const { user } = useAuth();
  useEventStream();
  useThemeSync();

  return (
    <HelpProvider>
      <div className="app-shell wm-shell">
        <WarmSidebar />
        <div className="app-main wm-main">
          <WarmTopbar />
          <div className="scroll-y wm-scroll">
            <Outlet />
          </div>
        </div>
      </div>
      <FeedbackButton variant="pills" />
      {user && <UsageTracker />}
      {user && <WhatsNewGate />}
    </HelpProvider>
  );
}
