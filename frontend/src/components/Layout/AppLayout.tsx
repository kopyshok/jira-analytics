import { useState, useCallback } from 'react';
import { Outlet, useNavigate } from 'react-router';
import { Layout, Button } from 'antd';
import { LogoutOutlined } from '@ant-design/icons';
import SideMenu from './SideMenu';
import LogoMark from './LogoMark';
import SyncIndicator from './SyncIndicator';
import GlobalTeamFilterButton from './GlobalTeamFilterButton';
import GlobalPeriodPicker from '../shared/GlobalPeriodPicker';
import BugReportButton from '../BugReportButton';
import { DARK_THEME } from '../../utils/constants';
import { useEventStream } from '../../hooks/useEventStream';
import { useAuth } from '../../hooks/useAuth';

const { Header, Sider, Content } = Layout;

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  useEventStream();

  const handleLogout = useCallback(async () => {
    await logout();
    navigate('/login', { replace: true });
  }, [logout, navigate]);

  return (
    <Layout style={{ minHeight: '100vh', background: 'transparent' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        breakpoint="lg"
        width={232}
        style={{ borderRight: `1px solid ${DARK_THEME.border}` }}
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
            padding: '28px 32px 48px',
            minHeight: 280,
            background: 'transparent',
          }}
        >
          <Outlet />
        </Content>
      </Layout>
      <BugReportButton />
    </Layout>
  );
}
