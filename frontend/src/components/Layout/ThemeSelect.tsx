import { Dropdown, Select } from 'antd';
import { Sun } from 'lucide-react';
import { APP_THEMES, type AppTheme } from '../../utils/constants';
import { useAppTheme } from '../../contexts/ThemeContext';
import { useSaveTheme } from '../../hooks/useTheme';

const THEME_ENTRIES = Object.entries(APP_THEMES) as [AppTheme, typeof APP_THEMES[AppTheme]][];

function themeLabel(def: typeof APP_THEMES[AppTheme]) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{
        width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
        background: def.tokens.primary, display: 'inline-block',
      }} />
      <span>{def.label}</span>
    </span>
  );
}

const OPTIONS = THEME_ENTRIES.map(([key, def]) => ({ value: key, label: themeLabel(def) }));

interface Props {
  width?: number;
  /** `icon` — круглая кнопка-значок с меню тем (оболочки скинов); по умолчанию — выпадающий список. */
  variant?: 'select' | 'icon';
}

export default function ThemeSelect({ width = 170, variant = 'select' }: Props) {
  const { theme } = useAppTheme();
  const saveTheme = useSaveTheme();
  if (variant === 'icon') {
    return (
      <Dropdown
        trigger={['click']}
        placement="bottomRight"
        menu={{
          selectable: true,
          selectedKeys: [theme],
          items: THEME_ENTRIES.map(([key, def]) => ({ key, label: themeLabel(def) })),
          onClick: ({ key }) => saveTheme(key as AppTheme),
        }}
      >
        <button
          type="button"
          className="theme-select-icon"
          aria-label={`Тема: ${APP_THEMES[theme].label}`}
          title={`Тема: ${APP_THEMES[theme].label}`}
          data-testid="theme-select"
        >
          <Sun size={18} strokeWidth={1.5} aria-hidden />
        </button>
      </Dropdown>
    );
  }
  return (
    <Select
      value={theme}
      options={OPTIONS}
      onChange={(v) => saveTheme(v as AppTheme)}
      size="small"
      variant="borderless"
      style={{ width }}
      popupMatchSelectWidth={false}
    />
  );
}
