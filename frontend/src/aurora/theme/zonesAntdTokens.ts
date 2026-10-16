import type { ThemeConfig } from 'antd';
import { buildAuroraAntdConfig } from './auroraAntdTokens';

const COBALT = '#2546A6';
const TEXT = '#17191C';
const TEXT_2 = '#5A5F66';
const BORDER = '#E1E3E8';
const BORDER_CONTROL = '#D5D8DE';
const SURFACE = '#FFFFFF';
const PAGE = '#F2F3F5';
const HEAD = '#F7F8FA';
const HOVER = '#F4F6FA';
const SELECTED = '#E9ECF6'; // кобальт 12% на белом — сплошной

const FONT_TEXT = "'Wix Madefor Text', 'Segoe UI', system-ui, sans-serif";
const FONT_MONO = "'JetBrains Mono', ui-monospace, monospace";

/**
 * Скин «Цветовые зоны»: конфиг AntD = Aurora light + поправки стиля.
 * Белые сплошные поверхности на светло-сером, рамка 1px, скругление 10, без теней,
 * главный цвет — кобальт.
 */
export function buildZonesAntdConfig(): ThemeConfig {
  const base = buildAuroraAntdConfig('light');
  return {
    ...base,
    token: {
      ...base.token,
      colorPrimary: COBALT,
      colorInfo: COBALT,
      colorLink: COBALT,
      // Статусы: светлые подложки заданы явно (производные от тёмных семян выходят
      // серыми), текст статусов — темнее, чтобы держать контраст 4.5:1 на подложке.
      colorSuccess: '#237A4B',
      colorSuccessBg: '#E6F2EA',
      colorSuccessBorder: '#A9D3BA',
      colorWarning: '#946200',
      colorWarningBg: '#FBF1DF',
      colorWarningBorder: '#E8C98F',
      colorError: '#C0352A',
      colorErrorBg: '#FBE9E7',
      colorErrorBorder: '#EFB1AA',
      colorInfoBg: SELECTED,
      colorInfoBorder: '#C5CFEA',
      colorPrimaryBg: SELECTED,
      colorPrimaryBgHover: '#DFE4F3',
      colorPrimaryBorder: '#C5CFEA',
      colorPrimaryBorderHover: '#9FB0DE',
      colorText: TEXT,
      colorTextHeading: TEXT,
      colorTextSecondary: TEXT_2,
      colorTextTertiary: '#6B7078',
      colorTextQuaternary: '#8A8F97',
      colorTextPlaceholder: '#7B8088',
      colorBorder: BORDER_CONTROL,
      colorBorderSecondary: BORDER,
      colorSplit: BORDER,
      colorBgBase: SURFACE,
      colorBgContainer: SURFACE,
      colorBgElevated: SURFACE,
      colorBgLayout: PAGE,
      colorFillAlter: HEAD,
      borderRadius: 8,
      borderRadiusLG: 10,
      borderRadiusSM: 6,
      controlHeight: 34,
      controlHeightSM: 28,
      controlHeightLG: 40,
      fontSize: 14,
      fontFamily: FONT_TEXT,
      fontFamilyCode: FONT_MONO,
      boxShadow: 'none',
      boxShadowSecondary: 'none',
      boxShadowTertiary: 'none',
      controlOutline: 'rgba(37,70,166,0.18)',
    },
    components: {
      ...base.components,
      Layout: { siderBg: SURFACE, headerBg: SURFACE, bodyBg: PAGE },
      Card: { colorBgContainer: SURFACE, headerBg: SURFACE, borderRadiusLG: 10 },
      Table: {
        colorBgContainer: SURFACE,
        headerBg: HEAD,
        headerColor: TEXT_2,
        headerSplitColor: 'transparent',
        rowHoverBg: HOVER,
        rowSelectedBg: SELECTED,
        rowSelectedHoverBg: '#DFE4F3',
        borderColor: BORDER,
        footerBg: HEAD,
      },
      Tabs: {
        inkBarColor: COBALT,
        itemColor: '#3F444B',
        itemHoverColor: COBALT,
        itemActiveColor: COBALT,
        itemSelectedColor: COBALT,
      },
      Menu: {
        itemBg: SURFACE,
        itemSelectedBg: SELECTED,
        itemSelectedColor: COBALT,
        itemHoverBg: HOVER,
      },
      Button: {
        primaryShadow: 'none',
        defaultShadow: 'none',
        dangerShadow: 'none',
        fontWeight: 600,
        defaultBorderColor: BORDER_CONTROL,
      },
      Segmented: {
        trackBg: '#EEF0F3',
        itemSelectedBg: COBALT,
        itemSelectedColor: '#FFFFFF',
        itemColor: '#3F444B',
      },
      Tag: { defaultBg: '#F2F3F5', defaultColor: '#3F444B' },
      Modal: { contentBg: SURFACE, headerBg: SURFACE, footerBg: SURFACE, titleFontSize: 18 },
      Drawer: { colorBgElevated: SURFACE },
      Select: {
        optionSelectedBg: SELECTED,
        optionSelectedColor: TEXT,
        optionActiveBg: HOVER,
        selectorBg: SURFACE,
      },
      Tooltip: { colorBgSpotlight: '#17191C' },
    },
  };
}
