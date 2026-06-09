import { Select } from 'antd';
import { APP_THEMES, type AppTheme } from '../../utils/constants';
import { useAppTheme } from '../../contexts/ThemeContext';
import { useSaveTheme } from '../../hooks/useTheme';

const OPTIONS = (Object.entries(APP_THEMES) as [AppTheme, typeof APP_THEMES[AppTheme]][]).map(
  ([key, def]) => ({
    value: key,
    label: (
      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{
          width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
          background: def.tokens.primary, display: 'inline-block',
        }} />
        <span>{def.label}</span>
        {def.isNew && (
          <span style={{
            fontSize: 9,
            fontWeight: 700,
            letterSpacing: '0.05em',
            padding: '1px 5px',
            borderRadius: 4,
            background: 'linear-gradient(90deg, #38bdf8, #a78bfa)',
            color: '#fff',
            marginLeft: 2,
          }}>NEW</span>
        )}
      </span>
    ),
  }),
);

interface Props {
  width?: number;
}

export default function ThemeSelect({ width = 170 }: Props) {
  const { theme } = useAppTheme();
  const saveTheme = useSaveTheme();
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
