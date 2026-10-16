import { useCallback, useState } from 'react';
import { Outlet, useNavigate } from 'react-router';
import { LogOut } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { trackAction } from '../../lib/usage/track';
import FeedbackButton from '../../components/feedback/FeedbackButton';
import WhatsNewGate from '../../components/release-notes/WhatsNewGate';
import GlobalTeamFilterButton from '../../components/Layout/GlobalTeamFilterButton';
import GlobalPeriodPicker from '../../components/shared/GlobalPeriodPicker';
import GlobalHelpButton from '../../components/Layout/GlobalHelpButton';
import SyncIndicator from '../../components/Layout/SyncIndicator';
import ThemeSelect from '../../components/Layout/ThemeSelect';
import OnboardingButton from '../../onboarding/OnboardingButton';
import { HelpProvider } from '../../contexts/HelpContext';
import { useEventStream } from '../../hooks/useEventStream';
import { useThemeSync } from '../../hooks/useTheme';
import { UsageTracker } from './AuroraShell';
import { NAV_GROUPS, findGroupForPath, useNavSections, type NavGroup } from './navConfig';

/** Постоянный номер группы («01 Обзор») — не сдвигается, если группа скрыта. */
function groupNumber(id: NavGroup['id']): string {
  return String(NAV_GROUPS.findIndex((g) => g.id === id) + 1).padStart(2, '0');
}

function initials(name: string): string {
  return name
    .split(' ')
    .map((w) => w[0] || '')
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

/**
 * Оболочка обложки «Швейцарская»: без бокового меню, двухъярусная навигация
 * на всю ширину. Ярус 1 — название, три нумерованные группы и все общие
 * элементы управления; ярус 2 — пункты выбранной группы. Ниже — прокручиваемое
 * содержимое страницы.
 */
export default function SwissShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  useEventStream();
  useThemeSync();

  const { groups, selectedKey, pathname } = useNavSections();
  // Выбор группы живёт, пока не сменился адрес: после перехода второй ярус
  // снова показывает группу текущей страницы.
  const [picked, setPicked] = useState<{ id: NavGroup['id']; path: string } | null>(null);
  const routeGroup = findGroupForPath(groups, pathname) ?? groups[0];
  const shownGroup = (picked && picked.path === pathname
    ? groups.find((g) => g.id === picked.id)
    : undefined) ?? routeGroup;

  const handleLogout = useCallback(async () => {
    await logout();
    trackAction('logout');
    navigate('/login', { replace: true });
  }, [logout, navigate]);

  return (
    <HelpProvider>
      <div className="sw-shell">
        <header className="sw-tier1">
          <div className="sw-tier1-left">
            <div className="sw-brand">
              <b>Jira Analytics</b>
              <span className="sw-version" title={`Версия ${__APP_VERSION__}`}>v{__APP_VERSION__}</span>
            </div>
            <nav className="sw-groups" aria-label="Группы разделов">
              {groups.map((g) => {
                const isShown = g.id === shownGroup?.id;
                const isCurrent = g.id === routeGroup?.id;
                return (
                  <button
                    key={g.id}
                    type="button"
                    className={`sw-group${isShown ? ' is-shown' : ''}${isCurrent ? ' is-current' : ''}`}
                    aria-expanded={isShown}
                    aria-controls="sw-tier2"
                    onClick={() => setPicked({ id: g.id, path: pathname })}
                  >
                    <span className="sw-group-num">{groupNumber(g.id)}</span>
                    {g.label}
                  </button>
                );
              })}
            </nav>
          </div>
          <div className="sw-controls">
            <SyncIndicator />
            {user && (
              <>
                <span data-tour="header-team" style={{ display: 'inline-flex' }}><GlobalTeamFilterButton /></span>
                <span data-tour="header-period" style={{ display: 'inline-flex' }}><GlobalPeriodPicker /></span>
                <OnboardingButton />
                <span data-tour="header-help" style={{ display: 'inline-flex' }}><GlobalHelpButton /></span>
                <span className="sw-theme" style={{ display: 'inline-flex' }}><ThemeSelect width={150} /></span>
                <span className="sw-user" title={user.display_name}>
                  <span className="sw-avatar" aria-hidden="true">{initials(user.display_name)}</span>
                  <span className="sw-user-name">{user.display_name}</span>
                </span>
                <button type="button" className="sw-icon-btn" title="Выйти" aria-label="Выйти" onClick={handleLogout}>
                  <LogOut size={18} strokeWidth={1.5} />
                </button>
              </>
            )}
          </div>
        </header>
        {shownGroup && (
          <nav id="sw-tier2" className="sw-tier2" aria-label={shownGroup.label}>
            {shownGroup.items.map(({ key, label }) => (
              <a
                key={key}
                href={key}
                className={`sw-item${selectedKey === key ? ' is-active' : ''}`}
                aria-current={selectedKey === key ? 'page' : undefined}
                onClick={(e) => {
                  // Обычный клик — переход внутри приложения; с Ctrl/Shift — новая вкладка браузера.
                  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
                  e.preventDefault();
                  navigate(key);
                }}
              >
                {label}
              </a>
            ))}
          </nav>
        )}
        <main className="sw-main scroll-y">
          <Outlet />
        </main>
      </div>
      <FeedbackButton />
      {user && <UsageTracker />}
      {user && <WhatsNewGate />}
    </HelpProvider>
  );
}
