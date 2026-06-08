import { theme as antdTheme } from 'antd';
import type { ThemeConfig } from 'antd';

export function buildAuroraAntdConfig(mode: 'dark' | 'light'): ThemeConfig {
  const isDark = mode === 'dark';
  return {
    algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      colorPrimary: isDark ? '#38bdf8' : '#0ea5e9',
      colorBgContainer: 'transparent',
      colorBgElevated: isDark ? 'rgba(20,25,40,0.95)' : 'rgba(255,255,255,0.95)',
      colorBgLayout: 'transparent',
      colorBorderSecondary: isDark ? 'rgba(255,255,255,0.10)' : 'rgba(60,90,160,0.12)',
      colorText: isDark ? '#eaf0fb' : '#16203a',
      colorTextSecondary: isDark ? '#b8c6e0' : '#3f4d6e',
      colorTextTertiary: isDark ? '#7f90b0' : '#707f9e',
      colorTextQuaternary: isDark ? '#5a6a85' : '#8b97b3',
      borderRadius: 12,
      borderRadiusLG: 20,
      colorLink: isDark ? '#a78bfa' : '#7c5cf6',
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
        inkBarColor: isDark ? '#38bdf8' : '#0ea5e9',
        itemActiveColor: isDark ? '#38bdf8' : '#0ea5e9',
        itemSelectedColor: isDark ? '#38bdf8' : '#0ea5e9',
      },
    },
  };
}
