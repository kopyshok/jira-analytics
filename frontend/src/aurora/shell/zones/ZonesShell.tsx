import { useCallback, useEffect, useState, useSyncExternalStore, type ReactNode } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router';
import { ConfigProvider, Dropdown } from 'antd';
import {
  CalendarRange,
  Database,
  LayoutDashboard,
  LogOut,
  Palette,
  PanelLeft,
  type LucideIcon as LucideIconType,
} from 'lucide-react';
import { useAuth } from '../../../hooks/useAuth';
import { useEventStream } from '../../../hooks/useEventStream';
import { useSaveTheme, useThemeSync } from '../../../hooks/useTheme';
import { useAppTheme } from '../../../contexts/ThemeContext';
import { HelpProvider } from '../../../contexts/HelpContext';
import { usePageView } from '../../../lib/usage/usePageView';
import { useHeartbeat } from '../../../lib/usage/useHeartbeat';
import { trackAction } from '../../../lib/usage/track';
import { APP_THEMES, type AppTheme } from '../../../utils/constants';
import FeedbackButton from '../../../components/feedback/FeedbackButton';
import WhatsNewGate from '../../../components/release-notes/WhatsNewGate';
import SyncIndicator from '../../../components/Layout/SyncIndicator';
import GlobalTeamFilterButton from '../../../components/Layout/GlobalTeamFilterButton';
import GlobalPeriodPicker from '../../../components/shared/GlobalPeriodPicker';
import GlobalHelpButton from '../../../components/Layout/GlobalHelpButton';
import OnboardingButton from '../../../onboarding/OnboardingButton';
import { navMatch, useNavSections, type NavGroupId } from '../navConfig';
import { buildZoneAccentTheme } from '../../theme/zonesAntdTokens';
import { ZonesBandContext, type ZonesBandSlots } from '../../../skins/zones/bandContext';

/**
 * Оболочка скина «Цветовые зоны»: тёмная колонка зон (Обзор / Планирование /
 * Данные), белая колонка пунктов выбранной зоны и сплошная полоса цвета зоны
 * над рабочей областью. Зона страницы — по группе меню из общего navConfig.
 * Классы zn-* — свои: .side-item / .topbar остаются только у Aurora.
 */

const ZONE_ICONS: Record<NavGroupId, LucideIconType> = {
  overview: LayoutDashboard,
  planning: CalendarRange,
  data: Database,
};

// Поправка темы AntD под зону — одна на зону, без пересборки на каждом рендере.
const ACCENT_THEMES = {
  overview: buildZoneAccentTheme('overview'),
  planning: buildZoneAccentTheme('planning'),
  data: buildZoneAccentTheme('data'),
} satisfies Record<NavGroupId, ReturnType<typeof buildZoneAccentTheme>>;

// Ниже этой ширины колонка пунктов не занимает место, а выезжает поверх.
const NARROW_MQ = '(max-width: 1199px)';
function subscribeNarrow(cb: () => void): () => void {
  const mq = window.matchMedia(NARROW_MQ);
  mq.addEventListener('change', cb);
  return () => mq.removeEventListener('change', cb);
}
const getNarrow = (): boolean => window.matchMedia(NARROW_MQ).matches;

function UsageTracker(): ReactNode {
  usePageView();
  useHeartbeat();
  return null;
}

function initials(name: string): string {
  return name
    .split(' ')
    .map((w) => w[0] || '')
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

function ThemeMenuButton() {
  const { theme } = useAppTheme();
  const saveTheme = useSaveTheme();
  const items = (Object.entries(APP_THEMES) as [AppTheme, (typeof APP_THEMES)[AppTheme]][]).map(
    ([key, def]) => ({
      key,
      label: (
        <span className="zn-theme-option">
          <span className="zn-theme-dot" style={{ background: def.tokens.primary }} />
          {def.label}
        </span>
      ),
    }),
  );
  return (
    <Dropdown
      trigger={['click']}
      placement="topLeft"
      menu={{
        items,
        selectable: true,
        selectedKeys: [theme],
        onClick: ({ key }) => { void saveTheme(key as AppTheme); },
      }}
    >
      <button
        type="button"
        className="zn-rail-btn"
        title={`Тема: ${APP_THEMES[theme].label}`}
        aria-label="Тема оформления"
        data-testid="zn-theme-button"
      >
        <Palette size={18} strokeWidth={1.6} />
      </button>
    </Dropdown>
  );
}

export default function ZonesShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  useEventStream();
  useThemeSync();

  const { groups, selectedKey } = useNavSections();
  const route = navMatch(location.pathname);
  const routeZone = route.group.id;

  // Выбранная плиткой зона живёт, пока не сменилась зона страницы.
  const [view, setView] = useState<{ route: NavGroupId; zone: NavGroupId }>({
    route: routeZone,
    zone: routeZone,
  });
  const wanted = view.route === routeZone ? view.zone : routeZone;
  const shown = groups.find((g) => g.id === wanted) ?? groups[0];

  const narrow = useSyncExternalStore(subscribeNarrow, getNarrow, () => false);
  const [collapsed, setCollapsed] = useState(false);
  const [overlayOpen, setOverlayOpen] = useState(false);
  const itemsVisible = narrow ? overlayOpen : !collapsed;

  const toggleItems = () => {
    if (narrow) setOverlayOpen((o) => !o);
    else setCollapsed((c) => !c);
  };

  const pickZone = (id: NavGroupId) => {
    setView({ route: routeZone, zone: id });
    if (narrow) setOverlayOpen((o) => (id === shown?.id ? !o : true));
    // Щелчок по открытой зоне сворачивает колонку пунктов, по другой — открывает.
    else setCollapsed((c) => (id === shown?.id ? !c : false));
  };

  // Зона страницы — на <html>: её акцент берут и всплывающие окна вне оболочки.
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute('data-zone', routeZone);
    return () => root.removeAttribute('data-zone');
  }, [routeZone]);
  const accentTheme = ACCENT_THEMES[routeZone];

  // Места в цветной полосе, куда страница переносит заголовок и фильтры.
  const [bandHead, setBandHead] = useState<HTMLDivElement | null>(null);
  const [bandTools, setBandTools] = useState<HTMLDivElement | null>(null);
  const [bandRows, setBandRows] = useState<HTMLDivElement | null>(null);
  // Объект мест запоминает компилятор React — пересобирается при смене мест или зоны.
  const band: ZonesBandSlots = { head: bandHead, tools: bandTools, rows: bandRows, zoneLabel: route.group.label };

  const go = (key: string) => {
    navigate(key);
    setOverlayOpen(false);
  };

  const handleLogout = useCallback(async () => {
    await logout();
    trackAction('logout');
    navigate('/login', { replace: true });
  }, [logout, navigate]);

  const appClass = [
    'zn-app',
    narrow ? 'is-narrow' : '',
    itemsVisible ? 'is-items-open' : 'is-items-closed',
  ].filter(Boolean).join(' ');

  return (
    <HelpProvider>
      <ConfigProvider theme={accentTheme}>
      <ZonesBandContext.Provider value={band}>
      <div className={appClass}>
        <nav className="zn-rail" aria-label="Зоны">
          {groups.map((g) => {
            const Icon = ZONE_ICONS[g.id];
            const isShown = itemsVisible && g.id === shown?.id;
            const isRoute = g.id === routeZone;
            // Залита зона, чьи пункты открыты; колонка скрыта — зона страницы.
            const isActive = itemsVisible ? isShown : isRoute;
            return (
              <button
                key={g.id}
                type="button"
                className={`zn-tile${isActive ? ' is-active' : ''}`}
                data-zone={g.id}
                aria-pressed={isShown}
                aria-current={isRoute ? 'page' : undefined}
                title={g.label}
                onClick={() => pickZone(g.id)}
              >
                <Icon size={22} strokeWidth={1.6} aria-hidden />
                <span className="zn-tile-label">{g.label}</span>
                <span className="zn-tile-stripe" aria-hidden />
              </button>
            );
          })}
          <div className="zn-rail-spacer" />
          <ThemeMenuButton />
          {user && (
            <>
              <button
                type="button"
                className="zn-rail-btn"
                title="Выйти"
                aria-label="Выйти"
                onClick={handleLogout}
              >
                <LogOut size={18} strokeWidth={1.6} />
              </button>
              <span className="zn-avatar" title={user.display_name} data-zone={routeZone}>
                {initials(user.display_name)}
              </span>
            </>
          )}
        </nav>

        {shown && (
          <aside
            className="zn-items"
            data-zone={shown.id}
            aria-label={`Пункты зоны «${shown.label}»`}
            hidden={!itemsVisible}
          >
            <div className="zn-brand">
              <span className="zn-brand-name">Jira Analytics</span>
              <span className="zn-brand-ver" title={`Версия ${__APP_VERSION__}`}>v{__APP_VERSION__}</span>
            </div>
            <div className="zn-items-title">{shown.label}</div>
            <div className="zn-items-list">
              {shown.items.map(({ key, label }) => {
                const active = selectedKey === key;
                return (
                  <button
                    key={key}
                    type="button"
                    className={`zn-item${active ? ' is-active' : ''}`}
                    aria-current={active ? 'page' : undefined}
                    onClick={() => go(key)}
                  >
                    <span className="zn-item-label">{label}</span>
                  </button>
                );
              })}
            </div>
            {user && <div className="zn-items-foot">{user.display_name}</div>}
          </aside>
        )}
        {narrow && overlayOpen && (
          <div className="zn-scrim" onClick={() => setOverlayOpen(false)} aria-hidden />
        )}

        <div className="zn-main">
          <header className="zn-band" data-zone={routeZone}>
            <div className="zn-band-top">
              <div className="zn-band-left">
                {narrow && (
                  <button
                    type="button"
                    className="zn-band-btn"
                    aria-label={itemsVisible ? 'Скрыть пункты зоны' : 'Показать пункты зоны'}
                    aria-expanded={itemsVisible}
                    title={itemsVisible ? 'Скрыть пункты зоны' : 'Показать пункты зоны'}
                    onClick={toggleItems}
                  >
                    <PanelLeft size={18} strokeWidth={1.6} />
                  </button>
                )}
                <div className="zn-band-head" ref={setBandHead} />
                {/* Страница без своего заголовка — рубрика и пункт меню. */}
                <div className="zn-page-head zn-band-default">
                  <div className="zn-page-eyebrow">{route.group.label}</div>
                  {route.item && <div className="zn-page-title">{route.item.label}</div>}
                </div>
              </div>
              <div className="zn-band-tools">
                <SyncIndicator />
                {user && (
                  <>
                    <span data-tour="header-team" style={{ display: 'inline-flex' }}><GlobalTeamFilterButton /></span>
                    <span data-tour="header-period" style={{ display: 'inline-flex' }}><GlobalPeriodPicker /></span>
                    <OnboardingButton />
                    <span data-tour="header-help" style={{ display: 'inline-flex' }}><GlobalHelpButton /></span>
                  </>
                )}
                <div className="zn-band-page-tools" ref={setBandTools} />
              </div>
            </div>
            <div className="zn-band-rows" ref={setBandRows} />
          </header>
          <main className="zn-content scroll-y">
            <Outlet />
          </main>
        </div>
      </div>
      <FeedbackButton />
      {user && <UsageTracker />}
      {user && <WhatsNewGate />}
      </ZonesBandContext.Provider>
      </ConfigProvider>
    </HelpProvider>
  );
}
