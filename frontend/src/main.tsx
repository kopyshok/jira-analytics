import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router';
import { App as AntApp, ConfigProvider, theme } from 'antd';
import ruRURaw from 'antd/locale/ru_RU';

// Vite CJS→ESM interop: antd's pre-bundled locale wraps the object under `.default`.
// Unwrap so ConfigProvider receives the actual locale object with DatePicker/Modal/etc keys.
const ruRU = ((ruRURaw as unknown as { default?: typeof ruRURaw }).default
  ?? ruRURaw) as typeof ruRURaw;
import dayjs from 'dayjs';
import 'dayjs/locale/ru';
import weekday from 'dayjs/plugin/weekday';
import localeData from 'dayjs/plugin/localeData';
import { router } from './routes';

dayjs.extend(weekday);
dayjs.extend(localeData);
dayjs.locale('ru');
import { DARK_THEME, FONTS } from './utils/constants';
import './index.css';
import './styles/print.css';

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
          fontFamily: FONTS.body,
          fontFamilyCode: FONTS.mono,
          fontSize: 14,
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
            contentFontSize: 32,
          },
          Typography: {
            fontWeightStrong: 700,
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
