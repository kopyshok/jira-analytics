import { useState, useCallback } from 'react';
import { Outlet, useNavigate } from 'react-router';
import { Layout, Button, Select } from 'antd';
import { LogoutOutlined, BgColorsOutlined } from '@ant-design/icons';
import SideMenu from './SideMenu';
import LogoMark from './LogoMark';
import SyncIndicator from './SyncIndicator';
import GlobalTeamFilterButton from './GlobalTeamFilterButton';
import GlobalPeriodPicker from '../shared/GlobalPeriodPicker';
import GlobalHelpButton from './GlobalHelpButton';
import FeedbackButton from '../feedback/FeedbackButton';
import WhatsNewGate from '../release-notes/WhatsNewGate';
import { HelpProvider } from '../../contexts/HelpContext';
import { DARK_THEME, APP_THEMES, type AppTheme } from '../../utils/constants';
import { useEventStream } from '../../hooks/useEventStream';
import { useAuth } from '../../hooks/useAuth';
import { useThemeSync, useSaveTheme } from '../../hooks/useTheme';
import { useAppTheme } from '../../contexts/ThemeContext';
import { usePageView } from '../../lib/usage/usePageView';
import { useHeartbeat } from '../../lib/usage/useHeartbeat';
import { trackAction } from '../../lib/usage/track';

function UsageTracker() {
  usePageView();
  useHeartbeat();
  return null;
}

const { Header, Sider, Content } = Layout;

const THEME_OPTIONS = (Object.entries(APP_THEMES) as [AppTheme, typeof APP_THEMES[AppTheme]][]).map(
  ([key, def]) => ({
    value: key,
    label: (
      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{
          width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
          background: def.tokens.primary, display: 'inline-block',
        }} />
        {def.label}
      </span>
    ),
  }),
);

export default function ClassicShell() {
  const [collapsed, setCollapsed] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { theme: currentTheme } = useAppTheme();
  const saveTheme = useSaveTheme();
  useEventStream();
  useThemeSync();

  const handleLogout = useCallback(async () => {
    await logout();
    trackAction('logout');
    navigate('/login', { replace: true });
  }, [logout, navigate]);

  return (
    <HelpProvider>
    <Layout style={{ minHeight: '100vh', background: 'transparent' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        breakpoint="lg"
        width={232}
        style={{
          borderRight: `1px solid ${DARK_THEME.border}`,
          position: 'sticky',
          top: 0,
          height: '100vh',
          overflowY: 'auto',
        }}
      >
        <LogoMark collapsed={collapsed} />
        <SideMenu />
      </Sider>
      <Layout style={{ background: 'transparent' }}>
        <Header
          style={{
            padding: '0 28px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: `1px solid ${DARK_THEME.border}`,
            background: 'rgba(9, 21, 39, 0.65)',
            backdropFilter: 'blur(8px)',
            height: 56,
            lineHeight: '56px',
          }}
        >
          <div
            style={{
              fontSize: 11,
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: DARK_THEME.textMuted,
              fontWeight: 600,
            }}
          >
            Анализ Jira · Планирование квартала
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <SyncIndicator />
            {user && (
              <>
                <GlobalTeamFilterButton />
                <GlobalPeriodPicker />
                <GlobalHelpButton />
                <Select
                  value={currentTheme}
                  options={THEME_OPTIONS}
                  onChange={(v) => saveTheme(v as AppTheme)}
                  size="small"
                  variant="borderless"
                  style={{ width: 150, color: 'rgba(255,255,255,0.55)' }}
                  popupMatchSelectWidth={false}
                />
                <Button
                  type="primary"
                  size="small"
                  icon={<BgColorsOutlined />}
                  onClick={() => saveTheme('aurora-dark')}
                  title="Включить Aurora"
                >
                  Aurora
                </Button>
                <span style={{ color: 'rgba(255,255,255,0.55)', fontSize: 13 }}>
                  {user.display_name}
                </span>
                <Button
                  type="text"
                  size="small"
                  icon={<LogoutOutlined />}
                  onClick={handleLogout}
                  style={{ color: 'rgba(255,255,255,0.35)' }}
                  title="Выйти"
                />
              </>
            )}
          </div>
        </Header>
        <Content
          style={{
            padding: '14px 32px 32px',
            minHeight: 280,
            background: 'transparent',
          }}
        >
          <Outlet />
        </Content>
      </Layout>
      <FeedbackButton />
      {user && <UsageTracker />}
      {user && <WhatsNewGate />}
    </Layout>
    </HelpProvider>
  );
}
