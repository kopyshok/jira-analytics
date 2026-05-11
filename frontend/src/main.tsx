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
import { APP_THEMES, FONTS, THEME_TOKENS_V2 } from './utils/constants';
import { ThemeProvider, useAppTheme } from './contexts/ThemeContext';
import './index.css';
import './styles/print.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

function ThemedApp() {
  const { theme: themeName } = useAppTheme();
  const t = APP_THEMES[themeName].tokens;
  const v2 = THEME_TOKENS_V2[themeName];
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
          Tag: {
            defaultBg: v2.surface.accent,
            defaultColor: v2.text.primary,
          },
          Tooltip: {
            colorBgSpotlight: v2.surface.accent,
            colorTextLightSolid: v2.text.primary,
          },
          Button: {
            defaultBg: v2.surface.card,
            defaultBorderColor: v2.border.default,
            defaultColor: v2.text.primary,
          },
          Input: {
            activeBorderColor: v2.accent.primary,
            hoverBorderColor: v2.accent.secondary,
          },
          Select: {
            optionSelectedBg: v2.surface.accent,
          },
          DatePicker: {
            activeBorderColor: v2.accent.primary,
          },
          Form: {
            labelColor: v2.text.secondary,
          },
          Alert: {
            colorInfoBg: v2.surface.accent,
            colorInfoBorder: v2.border.default,
          },
          Notification: {
            colorBgElevated: v2.surface.card,
          },
          Dropdown: {
            colorBgElevated: v2.surface.card,
          },
          Popover: {
            colorBgElevated: v2.surface.card,
          },
          Drawer: {
            colorBgElevated: v2.surface.card,
          },
          Spin: {
            colorPrimary: v2.accent.primary,
          },
          Empty: {
            colorTextDisabled: v2.text.muted,
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
