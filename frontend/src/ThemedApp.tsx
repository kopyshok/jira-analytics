import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router';
import { App as AntApp, ConfigProvider, theme } from 'antd';
import ruRURaw from 'antd/locale/ru_RU';

// Vite CJS→ESM interop: antd's pre-bundled locale wraps the object under `.default`.
// Unwrap so ConfigProvider receives the actual locale object with DatePicker/Modal/etc keys.
const ruRU = ((ruRURaw as unknown as { default?: typeof ruRURaw }).default
  ?? ruRURaw) as typeof ruRURaw;

import { router } from './routes';
import { APP_THEMES, FONTS } from './utils/constants';
import { useAppTheme } from './contexts/ThemeContext';
import { buildAuroraAntdConfig } from './aurora/theme/auroraAntdTokens';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

export default function ThemedApp() {
  const { theme: themeName, isAurora, mode } = useAppTheme();
  const t = APP_THEMES[themeName].tokens;

  const classicConfig = {
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
      Layout: { siderBg: t.sidebarBg, headerBg: t.sidebarBg, bodyBg: t.pageBg },
      Menu: {
        darkItemBg: t.sidebarBg,
        darkItemSelectedBg: t.darkAccent,
        darkItemColor: t.textMuted,
        darkItemSelectedColor: t.primary,
        darkItemHoverColor: t.primarySecondary,
      },
      Card: { colorBgContainer: t.cardBg, colorBorderSecondary: t.border },
      Table: {
        colorBgContainer: t.cardBg,
        headerBg: t.darkAccent,
        rowHoverBg: t.darkRows,
        borderColor: t.border,
      },
      Modal: { contentBg: t.cardBg, headerBg: t.cardBg },
      Statistic: { colorTextDescription: t.textMuted, contentFontSize: 32 },
      Typography: { fontWeightStrong: 700 },
      Tabs: {
        inkBarColor: t.primary,
        itemActiveColor: t.primary,
        itemSelectedColor: t.primary,
      },
      Collapse: { headerBg: t.darkAccent, contentBg: t.cardBg },
    },
  };

  const antdConfig = isAurora && mode ? buildAuroraAntdConfig(mode) : classicConfig;

  return (
    <ConfigProvider locale={ruRU} theme={antdConfig}>
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  );
}
