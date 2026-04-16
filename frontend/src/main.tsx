import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router';
import { App as AntApp, ConfigProvider, theme } from 'antd';
import ruRU from 'antd/locale/ru_RU';
import { router } from './routes';
import { DARK_THEME } from './utils/constants';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider
      locale={ruRU}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: DARK_THEME.cyanPrimary,
          colorBgContainer: DARK_THEME.cardBg,
          colorBgElevated: DARK_THEME.cardBg,
          colorBgLayout: DARK_THEME.pageBg,
          colorBorderSecondary: DARK_THEME.border,
          colorText: DARK_THEME.textPrimary,
          colorTextSecondary: DARK_THEME.textSecondary,
          colorTextTertiary: DARK_THEME.textMuted,
          colorTextQuaternary: DARK_THEME.textHint,
          borderRadius: 8,
          colorLink: DARK_THEME.cyanSecondary,
        },
        components: {
          Layout: {
            siderBg: DARK_THEME.sidebarBg,
            headerBg: DARK_THEME.sidebarBg,
            bodyBg: DARK_THEME.pageBg,
          },
          Menu: {
            darkItemBg: DARK_THEME.sidebarBg,
            darkItemSelectedBg: DARK_THEME.darkAccent,
            darkItemColor: DARK_THEME.textMuted,
            darkItemSelectedColor: DARK_THEME.cyanPrimary,
            darkItemHoverColor: DARK_THEME.cyanSecondary,
          },
          Card: {
            colorBgContainer: DARK_THEME.cardBg,
            colorBorderSecondary: DARK_THEME.border,
          },
          Table: {
            colorBgContainer: DARK_THEME.cardBg,
            headerBg: DARK_THEME.darkAccent,
            rowHoverBg: DARK_THEME.darkRows,
            borderColor: DARK_THEME.border,
          },
          Modal: {
            contentBg: DARK_THEME.cardBg,
            headerBg: DARK_THEME.cardBg,
          },
          Statistic: {
            colorTextDescription: DARK_THEME.textMuted,
          },
          Tabs: {
            inkBarColor: DARK_THEME.cyanPrimary,
            itemActiveColor: DARK_THEME.cyanPrimary,
            itemSelectedColor: DARK_THEME.cyanPrimary,
          },
          Collapse: {
            headerBg: DARK_THEME.darkAccent,
            contentBg: DARK_THEME.cardBg,
          },
        },
      }}
    >
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  </StrictMode>,
);
