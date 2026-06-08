import { Sun, Moon, Palette } from 'lucide-react';
import { useAppTheme } from '../../contexts/ThemeContext';
import { useSaveTheme } from '../../hooks/useTheme';
import type { AppTheme } from '../../utils/constants';

const CYCLE: AppTheme[] = ['aurora-dark', 'aurora-light', 'dark-blue'];

export function ThemeToggle() {
  const { theme, isAurora, mode } = useAppTheme();
  const saveTheme = useSaveTheme();

  const next = (): AppTheme => {
    const idx = CYCLE.indexOf(theme);
    return CYCLE[(idx + 1) % CYCLE.length] ?? 'aurora-dark';
  };

  const title = isAurora
    ? mode === 'dark'
      ? 'Aurora светлая →'
      : 'Классика →'
    : 'Aurora тёмная →';

  const Icon = isAurora ? (mode === 'dark' ? Sun : Palette) : Moon;

  return (
    <button className="icon-btn" title={title} onClick={() => saveTheme(next())}>
      <Icon size={17} strokeWidth={1.8} />
    </button>
  );
}
