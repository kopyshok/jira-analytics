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

const FONT_TEXT = "'Zones Digits', 'Wix Madefor Text', 'Segoe UI', system-ui, sans-serif";
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
      colorTextPlaceholder: '#6B7078',
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
      // Выключенный переключатель с подписью «Нет» — белый текст на сером ≥ 4.5:1.
      Switch: { colorTextQuaternary: '#6B7078', colorTextTertiary: '#5A5F66' },
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

/** Акцент зоны: главная кнопка, ссылки, выделения на белых поверхностях. */
export interface ZoneAccent {
  fill: string;
  hover: string;
  active: string;
  /** Текст акцентом на белом и на подложке выделения (контраст ≥ 4.5). */
  ink: string;
  tint: string;
  tintHover: string;
  border: string;
  borderHover: string;
  outline: string;
}

export const ZONE_ACCENTS: Record<'overview' | 'planning' | 'data', ZoneAccent> = {
  overview: {
    fill: COBALT, hover: '#1E3B8E', active: '#18307A', ink: COBALT,
    tint: SELECTED, tintHover: '#DFE4F3', border: '#C5CFEA', borderHover: '#9FB0DE',
    outline: 'rgba(37,70,166,0.18)',
  },
  planning: {
    fill: '#9A6F00', hover: '#845F00', active: '#6E5000', ink: '#8A6200',
    tint: '#FBF5E6', tintHover: '#F6EACC', border: '#E2C98F', borderHover: '#C9A34E',
    outline: 'rgba(154,111,0,0.22)',
  },
  data: {
    fill: '#2F3337', hover: '#24272A', active: '#1A1C1E', ink: '#2F3337',
    tint: '#EBECED', tintHover: '#E1E3E5', border: '#C6C9CD', borderHover: '#9DA2A8',
    outline: 'rgba(47,51,55,0.2)',
  },
};

/**
 * Поправка темы AntD под зону страницы — вложенный ConfigProvider оболочки
 * зон: на экранах «Планирования» главный цвет тёмно-горчичный, «Данных» — графит.
 */
export function buildZoneAccentTheme(zone: keyof typeof ZONE_ACCENTS): ThemeConfig {
  const a = ZONE_ACCENTS[zone];
  return {
    token: {
      colorPrimary: a.fill,
      colorPrimaryHover: a.hover,
      colorPrimaryActive: a.active,
      colorPrimaryText: a.ink,
      colorPrimaryTextHover: a.hover,
      colorPrimaryBg: a.tint,
      colorPrimaryBgHover: a.tintHover,
      colorPrimaryBorder: a.border,
      colorPrimaryBorderHover: a.borderHover,
      colorLink: a.ink,
      colorLinkHover: a.hover,
      colorLinkActive: a.active,
      controlOutline: a.outline,
    },
    components: {
      Tabs: { inkBarColor: a.fill, itemHoverColor: a.ink, itemActiveColor: a.ink, itemSelectedColor: a.ink },
      Segmented: { itemSelectedBg: a.fill },
      Menu: { itemSelectedBg: a.tint, itemSelectedColor: a.ink },
      Table: { rowSelectedBg: a.tint, rowSelectedHoverBg: a.tintHover },
      Select: { optionSelectedBg: a.tint },
    },
  };
}
