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
import { APP_THEMES, FONTS } from './utils/constants';
import { ThemeProvider, useAppTheme } from './contexts/ThemeContext';
import { installConsoleCapture } from './utils/consoleCapture';
import './index.css';
import './styles/print.css';
import './aurora/styles/aurora.css';

installConsoleCapture();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

function ThemedApp() {
  const { theme: themeName } = useAppTheme();
  const t = APP_THEMES[themeName].tokens;
  return (
    <ConfigProvider
      locale={ruRU}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: t.primary,
          colorBgContainer: t.cardBg,
          colorBgElevated: t.cardBg,
          colorBgLayout: t.pageBg,
          colorBorderSecondary: t.border,
          colorText: t.textPrimary,
          colorTextSecondary: t.textSecondary,
          colorTextTertiary: t.textMuted,
          colorTextQuaternary: t.textHint,
          borderRadius: 8,
          colorLink: t.primarySecondary,
          fontFamily: FONTS.body,
          fontFamilyCode: FONTS.mono,
          fontSize: 14,
        },
        components: {
          Layout: {
            siderBg: t.sidebarBg,
            headerBg: t.sidebarBg,
            bodyBg: t.pageBg,
          },
          Menu: {
            darkItemBg: t.sidebarBg,
            darkItemSelectedBg: t.darkAccent,
            darkItemColor: t.textMuted,
            darkItemSelectedColor: t.primary,
            darkItemHoverColor: t.primarySecondary,
          },
          Card: {
            colorBgContainer: t.cardBg,
            colorBorderSecondary: t.border,
          },
          Table: {
            colorBgContainer: t.cardBg,
            headerBg: t.darkAccent,
            rowHoverBg: t.darkRows,
            borderColor: t.border,
          },
          Modal: {
            contentBg: t.cardBg,
            headerBg: t.cardBg,
          },
          Statistic: {
            colorTextDescription: t.textMuted,
            contentFontSize: 32,
          },
          Typography: {
            fontWeightStrong: 700,
          },
          Tabs: {
            inkBarColor: t.primary,
            itemActiveColor: t.primary,
            itemSelectedColor: t.primary,
          },
          Collapse: {
            headerBg: t.darkAccent,
            contentBg: t.cardBg,
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
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <ThemedApp />
    </ThemeProvider>
  </StrictMode>,
);
