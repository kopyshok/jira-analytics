import { theme as antdTheme } from 'antd';
import type { ThemeConfig } from 'antd';

export function buildAuroraAntdConfig(mode: 'dark' | 'light'): ThemeConfig {
  const isDark = mode === 'dark';
  return {
    algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      colorPrimary: isDark ? '#38bdf8' : '#3b6ef5',
      colorBgContainer: 'transparent',
      colorBgElevated: isDark ? 'rgba(20,25,40,0.95)' : '#e6ebf2',
      colorBgLayout: 'transparent',
      colorBgBase: isDark ? '#080b16' : '#e6ebf2',
      colorBorderSecondary: isDark ? 'rgba(255,255,255,0.10)' : 'rgba(195,203,217,0.7)',
      colorText: isDark ? '#eaf0fb' : '#2a3142',
      colorTextSecondary: isDark ? '#b8c6e0' : '#3f4860',
      colorTextTertiary: isDark ? '#7f90b0' : '#5d6680',
      colorTextQuaternary: isDark ? '#5a6a85' : '#7a8298',
      borderRadius: isDark ? 12 : 14,
      borderRadiusLG: isDark ? 20 : 22,
      colorLink: isDark ? '#a78bfa' : '#2f8de8',
      colorSuccess: isDark ? '#34d399' : '#1f9e6f',
      colorWarning: isDark ? '#fbbf24' : '#d98a2b',
      colorError: isDark ? '#fb7185' : '#e05647',
      colorInfo: isDark ? '#38bdf8' : '#3b6ef5',
      fontFamily: "'Manrope', -apple-system, 'Segoe UI', sans-serif",
      fontFamilyCode: "'JetBrains Mono', ui-monospace, monospace",
      fontSize: 14,
    },
    components: {
      Layout: {
        siderBg: 'transparent',
        headerBg: 'transparent',
        bodyBg: 'transparent',
      },
      Menu: {
        darkItemBg: 'transparent',
        darkItemSelectedBg: 'transparent',
        itemBg: 'transparent',
      },
      Card: {
        colorBgContainer: 'transparent',
      },
      Table: {
        colorBgContainer: 'transparent',
        headerBg: 'transparent',
      },
      Modal: {
        contentBg: 'transparent',
        headerBg: 'transparent',
      },
      Tabs: {
        inkBarColor: isDark ? '#38bdf8' : '#3b6ef5',
        itemActiveColor: isDark ? '#38bdf8' : '#3b6ef5',
        itemSelectedColor: isDark ? '#38bdf8' : '#3b6ef5',
      },
    },
  };
}
