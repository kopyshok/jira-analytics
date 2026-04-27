import { useState } from 'react';
import { Outlet } from 'react-router';
import { Layout } from 'antd';
import SideMenu from './SideMenu';
import LogoMark from './LogoMark';
import SyncIndicator from './SyncIndicator';
import BugReportButton from '../BugReportButton';
import { DARK_THEME } from '../../utils/constants';
import { useEventStream } from '../../hooks/useEventStream';

const { Header, Sider, Content } = Layout;

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  useEventStream();

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
          <SyncIndicator />
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
