import type { ThemeConfig } from 'antd';
import { buildAuroraAntdConfig } from './auroraAntdTokens';

/* «Швейцарская»: белый лист, чёрный текст, один красно-оранжевый акцент.
 * Акцент #E5401F — линии, крупные цифры; для текста и заливки под белым
 * текстом — чуть глубже (#BE3119, контраст 5.8:1 — и на светлых подложках не ниже 4.5). Скруглений и теней нет:
 * выпадающие слои и окна очерчены линией 1px через «тень» без размытия. */
const INK = '#111111';
const INK_2 = '#3A3A3A';
const MUTED = '#5E5E5E';
const HINT = '#6E6E6E';
const LINE = '#E2E2E2';
const FILL = '#F4F4F4';
const WHITE = '#FFFFFF';
const ACCENT_INK = '#BE3119';
const HAIRLINE = `0 0 0 1px ${INK}`;
const FONT = "'Geologica', 'Segoe UI', Arial, sans-serif";

export function buildSwissAntdConfig(): ThemeConfig {
  const base = buildAuroraAntdConfig('light');
  return {
    ...base,
    token: {
      ...base.token,
      colorPrimary: INK,
      colorLink: INK,
      colorLinkHover: ACCENT_INK,
      colorLinkActive: ACCENT_INK,
      colorInfo: '#1F4FD1',
      colorSuccess: '#1E7A3E',
      colorWarning: '#9A6400',
      colorError: ACCENT_INK,
      // Подложки плашек — светлые сплошные тона (алгоритм из тёмных статусов даёт грязный оливковый).
      colorInfoBg: '#EEF2FB',
      colorInfoBorder: '#1F4FD1',
      colorSuccessBg: '#EDF5EF',
      colorSuccessBorder: '#1E7A3E',
      colorWarningBg: '#FBF5E8',
      colorWarningBorder: '#9A6400',
      colorErrorBg: '#FCEEEA',
      colorErrorBorder: ACCENT_INK,
      colorText: INK,
      colorTextHeading: INK,
      colorTextSecondary: MUTED,
      colorTextTertiary: HINT,
      colorTextQuaternary: '#8A8A8A',
      // Подсказка в пустом поле — текст, ему нужен контраст 4.5:1 (#8A8A8A даёт 3.4).
      colorTextPlaceholder: '#6E6E6E',
      // Недоступное — светлее обычного, но читается (4.5:1 на белом).
      colorTextDisabled: '#767676',
      colorTextDescription: MUTED,
      colorBorder: INK,
      colorBorderSecondary: LINE,
      colorSplit: LINE,
      colorBgBase: WHITE,
      colorBgContainer: WHITE,
      colorBgLayout: WHITE,
      colorBgElevated: WHITE,
      colorBgSpotlight: INK,
      colorFillAlter: FILL,
      colorFillSecondary: FILL,
      colorFillTertiary: FILL,
      colorFillQuaternary: '#FAFAFA',
      controlItemBgHover: FILL,
      controlItemBgActive: FILL,
      controlItemBgActiveHover: '#EDEDED',
      controlOutline: 'rgba(17,17,17,0.18)',
      borderRadius: 0,
      borderRadiusLG: 0,
      borderRadiusSM: 0,
      borderRadiusXS: 0,
      borderRadiusOuter: 0,
      boxShadow: HAIRLINE,
      boxShadowSecondary: HAIRLINE,
      boxShadowTertiary: 'none',
      fontFamily: FONT,
      fontFamilyCode: "'JetBrains Mono', ui-monospace, monospace",
      fontSize: 13,
      controlHeight: 32,
      controlHeightSM: 24,
      controlHeightLG: 40,
      wireframe: false,
    },
    components: {
      ...base.components,
      Button: {
        colorPrimary: ACCENT_INK,
        colorPrimaryHover: INK,
        colorPrimaryActive: '#000000',
        primaryColor: WHITE,
        primaryShadow: 'none',
        defaultShadow: 'none',
        dangerShadow: 'none',
        defaultBorderColor: INK,
        defaultColor: INK,
        defaultBg: WHITE,
        defaultHoverBg: FILL,
        defaultHoverColor: INK,
        defaultHoverBorderColor: INK,
        defaultActiveBg: '#EDEDED',
        defaultActiveColor: INK,
        defaultActiveBorderColor: INK,
        textHoverBg: FILL,
        fontWeight: 500,
      },
      Table: {
        colorBgContainer: WHITE,
        headerBg: WHITE,
        headerColor: INK,
        headerSplitColor: 'transparent',
        headerSortActiveBg: FILL,
        headerSortHoverBg: FILL,
        fixedHeaderSortActiveBg: FILL,
        bodySortBg: '#FAFAFA',
        borderColor: LINE,
        rowHoverBg: FILL,
        rowSelectedBg: FILL,
        rowSelectedHoverBg: '#EDEDED',
        rowExpandedBg: WHITE,
        footerBg: WHITE,
        headerBorderRadius: 0,
        cellPaddingBlock: 6,
        cellPaddingInline: 8,
        cellPaddingBlockMD: 5,
        cellPaddingInlineMD: 8,
        cellPaddingBlockSM: 4,
        cellPaddingInlineSM: 6,
      },
      Tabs: {
        inkBarColor: INK,
        itemColor: MUTED,
        itemHoverColor: INK,
        itemActiveColor: INK,
        itemSelectedColor: INK,
        titleFontSize: 14,
        horizontalItemGutter: 32,
        cardBg: WHITE,
      },
      Menu: {
        itemBg: 'transparent',
        subMenuItemBg: 'transparent',
        itemColor: INK_2,
        itemHoverColor: INK,
        itemHoverBg: FILL,
        itemActiveBg: FILL,
        itemSelectedBg: FILL,
        itemSelectedColor: INK,
        groupTitleColor: MUTED,
        itemBorderRadius: 0,
        subMenuItemBorderRadius: 0,
        itemMarginInline: 0,
      },
      Segmented: {
        trackBg: WHITE,
        trackPadding: 0,
        itemColor: INK,
        itemHoverColor: INK,
        itemHoverBg: FILL,
        itemActiveBg: '#EDEDED',
        itemSelectedBg: INK,
        itemSelectedColor: WHITE,
      },
      Tag: {
        defaultBg: WHITE,
        defaultColor: INK,
      },
      Select: {
        selectorBg: WHITE,
        optionSelectedBg: FILL,
        optionSelectedColor: INK,
        optionSelectedFontWeight: 700,
        optionActiveBg: FILL,
      },
      Modal: {
        contentBg: WHITE,
        headerBg: WHITE,
        footerBg: WHITE,
        titleColor: INK,
        titleFontSize: 18,
      },
      Drawer: {
        colorBgElevated: WHITE,
      },
      Card: {
        colorBgContainer: WHITE,
        headerBg: 'transparent',
        headerFontSize: 14,
      },
      Tooltip: {
        colorBgSpotlight: INK,
        colorTextLightSolid: WHITE,
      },
      Progress: {
        defaultColor: INK,
        remainingColor: LINE,
      },
      Collapse: {
        headerBg: WHITE,
        contentBg: WHITE,
      },
      Statistic: {
        contentFontSize: 32,
      },
    },
  };
}
